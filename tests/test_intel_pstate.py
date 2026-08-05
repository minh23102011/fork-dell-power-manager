from pathlib import Path

from powerdeck_backends.cpu.intel_pstate import IntelPstateReader


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{value}\n", encoding="utf-8")


def _make_policy(
    root: Path,
    name: str,
    *,
    driver: str = "intel_pstate",
    governors: str = "performance powersave",
    governor: str = "powersave",
    minimum_khz: object = 400_000,
    maximum_khz: object = 5_000_000,
) -> Path:
    policy = root / name
    _write(policy / "scaling_driver", driver)
    _write(policy / "scaling_available_governors", governors)
    _write(policy / "scaling_governor", governor)
    _write(policy / "cpuinfo_min_freq", minimum_khz)
    _write(policy / "cpuinfo_max_freq", maximum_khz)
    return policy


def test_reads_intel_pstate_and_cpufreq_capabilities(
    tmp_path: Path,
) -> None:
    cpuinfo = tmp_path / "proc" / "cpuinfo"
    cpufreq = tmp_path / "cpufreq"
    intel_pstate = tmp_path / "intel_pstate"
    _write(
        cpuinfo,
        "processor : 0\nmodel name : 13th Gen Intel(R) Core(TM) i7-1355U",
    )
    _make_policy(cpufreq, "policy0")
    _write(intel_pstate / "status", "active")
    _write(intel_pstate / "no_turbo", 0)
    _write(intel_pstate / "min_perf_pct", 8)
    _write(intel_pstate / "max_perf_pct", 100)

    capabilities = IntelPstateReader(
        cpuinfo,
        cpufreq,
        intel_pstate,
    ).read_capabilities()

    assert capabilities.model_name == "13th Gen Intel(R) Core(TM) i7-1355U"
    assert capabilities.scaling_driver == "intel_pstate"
    assert capabilities.available_governors == ("performance", "powersave")
    assert capabilities.current_governor == "powersave"
    assert capabilities.minimum_frequency_mhz == 400.0
    assert capabilities.maximum_frequency_mhz == 5000.0
    assert capabilities.intel_pstate_status == "active"
    assert capabilities.turbo_control is True
    assert capabilities.min_performance_control is True
    assert capabilities.max_performance_control is True


def test_multiple_policies_are_sorted_and_aggregated(
    tmp_path: Path,
) -> None:
    cpufreq = tmp_path / "cpufreq"
    _make_policy(
        cpufreq,
        "policy10",
        governors="powersave performance schedutil",
        minimum_khz=600_000,
        maximum_khz=4_600_000,
    )
    _make_policy(
        cpufreq,
        "policy2",
        governors="performance powersave",
        minimum_khz=400_000,
        maximum_khz=5_000_000,
    )

    capabilities = IntelPstateReader(
        tmp_path / "cpuinfo",
        cpufreq,
        tmp_path / "intel_pstate",
    ).read_capabilities()

    assert capabilities.available_governors == (
        "performance",
        "powersave",
        "schedutil",
    )
    assert capabilities.minimum_frequency_mhz == 400.0
    assert capabilities.maximum_frequency_mhz == 5000.0


def test_mixed_driver_or_governor_has_no_false_consensus(
    tmp_path: Path,
) -> None:
    cpufreq = tmp_path / "cpufreq"
    _make_policy(
        cpufreq,
        "policy0",
        driver="intel_pstate",
        governor="powersave",
    )
    _make_policy(
        cpufreq,
        "policy1",
        driver="intel_cpufreq",
        governor="schedutil",
    )

    capabilities = IntelPstateReader(
        tmp_path / "cpuinfo",
        cpufreq,
        tmp_path / "intel_pstate",
    ).read_capabilities()

    assert capabilities.scaling_driver is None
    assert capabilities.current_governor is None


def test_frequency_reader_falls_back_to_scaling_limits(
    tmp_path: Path,
) -> None:
    cpufreq = tmp_path / "cpufreq"
    policy = _make_policy(cpufreq, "policy0")
    (policy / "cpuinfo_min_freq").unlink()
    (policy / "cpuinfo_max_freq").unlink()
    _write(policy / "scaling_min_freq", 800_000)
    _write(policy / "scaling_max_freq", 3_900_000)

    capabilities = IntelPstateReader(
        tmp_path / "cpuinfo",
        cpufreq,
        tmp_path / "intel_pstate",
    ).read_capabilities()

    assert capabilities.minimum_frequency_mhz == 800.0
    assert capabilities.maximum_frequency_mhz == 3900.0


def test_malformed_frequencies_are_ignored(tmp_path: Path) -> None:
    cpufreq = tmp_path / "cpufreq"
    _make_policy(
        cpufreq,
        "policy0",
        minimum_khz="not-a-number",
        maximum_khz=-1,
    )

    capabilities = IntelPstateReader(
        tmp_path / "cpuinfo",
        cpufreq,
        tmp_path / "intel_pstate",
    ).read_capabilities()

    assert capabilities.minimum_frequency_mhz is None
    assert capabilities.maximum_frequency_mhz is None


def test_passive_intel_pstate_driver_is_reported(
    tmp_path: Path,
) -> None:
    cpufreq = tmp_path / "cpufreq"
    intel_pstate = tmp_path / "intel_pstate"
    _make_policy(
        cpufreq,
        "policy0",
        driver="intel_cpufreq",
        governor="schedutil",
    )
    _write(intel_pstate / "status", "passive")

    capabilities = IntelPstateReader(
        tmp_path / "cpuinfo",
        cpufreq,
        intel_pstate,
    ).read_capabilities()

    assert capabilities.scaling_driver == "intel_cpufreq"
    assert capabilities.current_governor == "schedutil"
    assert capabilities.intel_pstate_status == "passive"


def test_missing_interfaces_return_empty_capabilities(
    tmp_path: Path,
) -> None:
    capabilities = IntelPstateReader(
        tmp_path / "missing-cpuinfo",
        tmp_path / "missing-cpufreq",
        tmp_path / "missing-intel-pstate",
    ).read_capabilities()

    assert capabilities.model_name is None
    assert capabilities.scaling_driver is None
    assert capabilities.available_governors == ()
    assert capabilities.current_governor is None
    assert capabilities.minimum_frequency_mhz is None
    assert capabilities.maximum_frequency_mhz is None
    assert capabilities.intel_pstate_status is None
    assert capabilities.turbo_control is False
    assert capabilities.max_performance_control is False
    assert capabilities.min_performance_control is False
