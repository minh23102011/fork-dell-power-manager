#include "mainwindow.hpp"

#include <algorithm>
#include <utility>

#include <QCheckBox>
#include <QComboBox>
#include <QDBusConnection>
#include <QDBusError>
#include <QDBusInterface>
#include <QDBusPendingCallWatcher>
#include <QDBusPendingReply>
#include <QDoubleSpinBox>
#include <QFormLayout>
#include <QFrame>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QIcon>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonValue>
#include <QLabel>
#include <QPainter>
#include <QPushButton>
#include <QScrollArea>
#include <QSizePolicy>
#include <QSpinBox>
#include <QStackedWidget>
#include <QTabBar>
#include <QTimer>
#include <QVBoxLayout>
#include <QWidget>

namespace {
constexpr auto kSystemService = "org.powerdeck.System1";
constexpr auto kSystemPath = "/org/powerdeck/System1";
constexpr auto kSystemInterface = "org.powerdeck.System1";
constexpr auto kAgentService = "org.powerdeck.Agent1";
constexpr auto kAgentPath = "/org/powerdeck/Agent1";
constexpr auto kAgentInterface = "org.powerdeck.Agent1";

QFrame* surface(QWidget* parent = nullptr) {
    auto* frame = new QFrame(parent);
    frame->setObjectName("surface");
    frame->setFrameShape(QFrame::NoFrame);
    return frame;
}

QWidget* pageHeader(
    const QString& title,
    const QString& subtitle,
    QWidget* parent = nullptr
) {
    auto* widget = new QWidget(parent);
    auto* layout = new QVBoxLayout(widget);
    layout->setContentsMargins(0, 4, 0, 2);
    layout->setSpacing(5);

    auto* titleLabel = new QLabel(title, widget);
    titleLabel->setObjectName("pageTitle");
    layout->addWidget(titleLabel);

    auto* subtitleLabel = new QLabel(subtitle, widget);
    subtitleLabel->setObjectName("pageSubtitle");
    subtitleLabel->setWordWrap(true);
    layout->addWidget(subtitleLabel);
    return widget;
}

QWidget* sectionHeader(
    const QString& title,
    const QString& subtitle,
    QWidget* parent = nullptr
) {
    auto* widget = new QWidget(parent);
    auto* layout = new QVBoxLayout(widget);
    layout->setContentsMargins(0, 8, 0, 0);
    layout->setSpacing(3);

    auto* titleLabel = new QLabel(title, widget);
    titleLabel->setObjectName("sectionTitle");
    layout->addWidget(titleLabel);

    if (!subtitle.isEmpty()) {
        auto* subtitleLabel = new QLabel(subtitle, widget);
        subtitleLabel->setObjectName("mutedText");
        subtitleLabel->setWordWrap(true);
        layout->addWidget(subtitleLabel);
    }
    return widget;
}

QWidget* statBlock(
    const QString& title,
    QLabel*& valueLabel,
    const QString& description,
    QWidget* parent = nullptr
) {
    auto* block = new QWidget(parent);
    block->setObjectName("statBlock");
    auto* layout = new QVBoxLayout(block);
    layout->setContentsMargins(18, 16, 18, 16);
    layout->setSpacing(5);

    auto* titleLabel = new QLabel(title, block);
    titleLabel->setObjectName("statLabel");
    layout->addWidget(titleLabel);

    valueLabel = new QLabel(QStringLiteral("Loading…"), block);
    valueLabel->setObjectName("statValue");
    valueLabel->setTextInteractionFlags(Qt::TextSelectableByMouse);
    layout->addWidget(valueLabel);

    auto* descriptionLabel = new QLabel(description, block);
    descriptionLabel->setObjectName("statDescription");
    descriptionLabel->setWordWrap(true);
    layout->addWidget(descriptionLabel);
    layout->addStretch();
    return block;
}

QWidget* settingRow(
    const QString& title,
    const QString& subtitle,
    QWidget* control,
    QWidget* parent = nullptr
) {
    auto* row = new QWidget(parent);
    row->setObjectName("settingRow");
    auto* layout = new QHBoxLayout(row);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(22);

    auto* text = new QWidget(row);
    auto* textLayout = new QVBoxLayout(text);
    textLayout->setContentsMargins(0, 0, 0, 0);
    textLayout->setSpacing(3);

    auto* titleLabel = new QLabel(title, text);
    titleLabel->setObjectName("settingTitle");
    textLayout->addWidget(titleLabel);

    if (!subtitle.isEmpty()) {
        auto* subtitleLabel = new QLabel(subtitle, text);
        subtitleLabel->setObjectName("mutedText");
        subtitleLabel->setWordWrap(true);
        textLayout->addWidget(subtitleLabel);
    }

    layout->addWidget(text, 1);
    layout->addWidget(control, 0, Qt::AlignRight | Qt::AlignVCenter);
    return row;
}

QFrame* divider(QWidget* parent = nullptr) {
    auto* line = new QFrame(parent);
    line->setObjectName("divider");
    line->setFrameShape(QFrame::HLine);
    line->setFixedHeight(1);
    return line;
}

QFrame* verticalDivider(QWidget* parent = nullptr) {
    auto* line = new QFrame(parent);
    line->setObjectName("verticalDivider");
    line->setFrameShape(QFrame::VLine);
    line->setFixedWidth(1);
    return line;
}

QWidget* scrollPage(QWidget* content) {
    content->setMaximumWidth(1440);
    content->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);

    auto* shell = new QWidget;
    shell->setObjectName("pageShell");
    auto* shellLayout = new QHBoxLayout(shell);
    shellLayout->setContentsMargins(24, 18, 24, 28);
    shellLayout->setSpacing(0);
    shellLayout->addStretch(1);
    shellLayout->addWidget(content, 12, Qt::AlignTop);
    shellLayout->addStretch(1);

    auto* scroll = new QScrollArea;
    scroll->setObjectName("pageScroll");
    scroll->setWidgetResizable(true);
    scroll->setFrameShape(QFrame::NoFrame);
    scroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    scroll->setWidget(shell);
    return scroll;
}

QString optionalString(const QJsonObject& object, const QString& key) {
    const auto value = object.value(key);
    return value.isString() ? value.toString() : QStringLiteral("Unavailable");
}

QString wattsText(const QJsonValue& value) {
    if (!value.isDouble()) {
        return QStringLiteral("Unavailable");
    }
    return QString::number(value.toDouble(), 'f', 2) + QStringLiteral(" W");
}

// PowerDeck charging mode descriptions follow Dell Power Manager semantics.
QString chargingModeDescription(const QString& mode) {
    const auto normalized = mode.trimmed().toLower();
    if (normalized == QStringLiteral("express")) {
        return QStringLiteral(
            "Express (Fast): prioritizes charging speed using Dell fast-charge "
            "behavior. It can trade some long-term battery health for faster charging."
        );
    }
    if (normalized == QStringLiteral("standard")) {
        return QStringLiteral(
            "Standard: charges at a moderate rate and balances charge time with "
            "everyday battery use."
        );
    }
    if (normalized == QStringLiteral("adaptive")) {
        return QStringLiteral(
            "Adaptive: firmware automatically adjusts charging behavior around "
            "your typical usage pattern."
        );
    }
    if (normalized == QStringLiteral("primarily_ac")) {
        return QStringLiteral(
            "Primarily AC: intended for systems that stay plugged in most of the "
            "time and avoids keeping the battery at full charge."
        );
    }
    if (normalized == QStringLiteral("custom")) {
        return QStringLiteral(
            "Custom: uses the start and stop thresholds below. Applying thresholds "
            "also activates Custom mode."
        );
    }
    return QStringLiteral("Select a charging mode to see what the firmware policy does.");
}

QString thermalProfileDescription(const QString& profile) {
    const auto normalized = profile.trimmed().toLower();
    if (normalized == QStringLiteral("cool")) {
        return QStringLiteral(
            "Cool: prioritizes lower surface temperature. Firmware may increase "
            "fan activity and reduce performance to stay cooler."
        );
    }
    if (normalized == QStringLiteral("quiet")) {
        return QStringLiteral(
            "Quiet: prioritizes lower fan noise. Firmware may reduce performance "
            "and allow a warmer surface temperature."
        );
    }
    if (normalized == QStringLiteral("balanced")) {
        return QStringLiteral(
            "Balanced: balances performance, fan noise and system temperature "
            "for normal use."
        );
    }
    if (normalized == QStringLiteral("performance")) {
        return QStringLiteral(
            "Performance: prioritizes sustained performance. Firmware may use "
            "more aggressive cooling and produce more fan noise."
        );
    }
    return QStringLiteral("Select a cooling profile to see how firmware will behave.");
}

QString humanDbusError(const QString& text) {
    QJsonParseError error;
    const auto document = QJsonDocument::fromJson(text.toUtf8(), &error);
    if (error.error != QJsonParseError::NoError || !document.isObject()) {
        return text;
    }

    const auto object = document.object();
    const auto details = object.value(QStringLiteral("details")).toObject();
    const auto reason = details.value(QStringLiteral("reason")).toString();
    if (reason.contains(
            QStringLiteral("no agent is available"),
            Qt::CaseInsensitive
        )) {
        return QStringLiteral(
            "Power setting change was denied because this session has no "
            "Polkit authentication agent."
        );
    }

    const auto message = object.value(QStringLiteral("message")).toString();
    return message.isEmpty() ? text : message;
}
}  // namespace

class SwitchCheckBox final : public QCheckBox {
public:
    explicit SwitchCheckBox(
        const QString& text = QString(),
        QWidget* parent = nullptr
    )
        : QCheckBox(text, parent) {
        setCursor(Qt::PointingHandCursor);
        setFocusPolicy(Qt::StrongFocus);
    }

    QSize sizeHint() const override {
        constexpr int kTrackWidth = 38;
        constexpr int kTrackHeight = 22;
        constexpr int kGap = 8;
        const auto metrics = QFontMetrics(font());
        const int textWidth = text().isEmpty() ? 0 : metrics.horizontalAdvance(text());
        const int width = kTrackWidth + (text().isEmpty() ? 0 : kGap + textWidth) + 6;
        const int height = std::max(kTrackHeight, metrics.height()) + 4;
        return {width, height};
    }

protected:
    void paintEvent(QPaintEvent*) override {
        constexpr int kTrackWidth = 38;
        constexpr int kTrackHeight = 22;
        constexpr int kKnobSize = 18;
        constexpr int kPadding = 2;

        QPainter painter(this);
        painter.setRenderHint(QPainter::Antialiasing);

        const QRect widgetRect = rect();
        const QRect trackRect(
            0,
            (widgetRect.height() - kTrackHeight) / 2,
            kTrackWidth,
            kTrackHeight
        );

        QColor trackColor = QColor("#3a4a53");
        QColor borderColor = QColor("#4f6d79");
        QColor knobColor = QColor("#f4fbff");
        QColor textColor = isEnabled() ? QColor("#e3ecf2") : QColor("#728189");

        if (!isEnabled()) {
            trackColor = QColor("#151b1f");
            borderColor = QColor("#3b4a52");
            knobColor = QColor("#66757c");
        } else if (isChecked()) {
            trackColor = QColor("#8fd9ea");
            borderColor = QColor("#8fd9ea");
            knobColor = QColor("#ffffff");
        }

        painter.setPen(QPen(borderColor, 1));
        painter.setBrush(trackColor);
        painter.drawRoundedRect(trackRect, kTrackHeight / 2.0, kTrackHeight / 2.0);

        const int knobX = isChecked()
            ? trackRect.right() - kKnobSize - kPadding + 1
            : trackRect.left() + kPadding;
        const QRect knobRect(
            knobX,
            trackRect.top() + kPadding,
            kKnobSize,
            kKnobSize
        );
        painter.setPen(Qt::NoPen);
        painter.setBrush(knobColor);
        painter.drawEllipse(knobRect);

        if (hasFocus()) {
            painter.setPen(QPen(QColor("#a5e3f0"), 1));
            painter.setBrush(Qt::NoBrush);
            painter.drawRoundedRect(
                trackRect.adjusted(-2, -2, 2, 2),
                (kTrackHeight + 4) / 2.0,
                (kTrackHeight + 4) / 2.0
            );
        }

        if (!text().isEmpty()) {
            painter.setPen(textColor);
            const QRect textRect(
                trackRect.right() + 8,
                0,
                widgetRect.width() - trackRect.width() - 8,
                widgetRect.height()
            );
            painter.drawText(textRect, Qt::AlignVCenter | Qt::AlignLeft, text());
        }
    }
};


MainWindow::MainWindow(QWidget* parent) : QMainWindow(parent) {
    setWindowTitle(QStringLiteral("PowerDeck"));
    resize(1280, 800);
    setMinimumSize(960, 620);
    buildUi();
    installStyle();
    refreshAll();

    telemetryTimer_ = new QTimer(this);
    telemetryTimer_->setInterval(1500);
    connect(telemetryTimer_, &QTimer::timeout, this, &MainWindow::refreshTelemetry);
    telemetryTimer_->start();
}

void MainWindow::buildUi() {
    auto* root = new QWidget(this);
    root->setObjectName("appRoot");
    auto* rootLayout = new QVBoxLayout(root);
    rootLayout->setContentsMargins(20, 16, 20, 14);
    rootLayout->setSpacing(12);

    auto* topbar = new QFrame(root);
    topbar->setObjectName("topbar");
    auto* topbarLayout = new QHBoxLayout(topbar);
    topbarLayout->setContentsMargins(12, 8, 12, 8);
    topbarLayout->setSpacing(14);

    auto* brandMark = new QLabel(QStringLiteral("PD"), topbar);
    brandMark->setObjectName("brandMark");
    brandMark->setAlignment(Qt::AlignCenter);
    brandMark->setFixedSize(38, 38);
    topbarLayout->addWidget(brandMark);

    auto* brandCopy = new QWidget(topbar);
    auto* brandLayout = new QVBoxLayout(brandCopy);
    brandLayout->setContentsMargins(0, 0, 0, 0);
    brandLayout->setSpacing(0);

    auto* brandTitle = new QLabel(QStringLiteral("PowerDeck"), brandCopy);
    brandTitle->setObjectName("appTitle");
    brandLayout->addWidget(brandTitle);

    auto* brandSubtitle = new QLabel(
        QStringLiteral("Native power control"),
        brandCopy
    );
    brandSubtitle->setObjectName("brandSubtitle");
    brandLayout->addWidget(brandSubtitle);
    topbarLayout->addWidget(brandCopy);

    navigation_ = new QTabBar(topbar);
    navigation_->setObjectName("mainTabs");
    navigation_->setDrawBase(false);
    navigation_->setExpanding(false);
    navigation_->setUsesScrollButtons(false);
    navigation_->addTab(QStringLiteral("Battery"));
    navigation_->addTab(QStringLiteral("Thermal"));
    navigation_->addTab(QStringLiteral("Battery Saver"));
    topbarLayout->addSpacing(12);
    topbarLayout->addWidget(navigation_);
    topbarLayout->addStretch(1);

    statusLabel_ = new QLabel(QStringLiteral("Connected"), topbar);
    statusLabel_->setObjectName("connectionStatus");
    statusLabel_->setMaximumWidth(360);
    statusLabel_->setWordWrap(true);
    topbarLayout->addWidget(statusLabel_);

    auto* refresh = new QPushButton(
        QIcon::fromTheme(QStringLiteral("view-refresh-symbolic")),
        QStringLiteral("Refresh"),
        topbar
    );
    refresh->setObjectName("toolbarButton");
    connect(refresh, &QPushButton::clicked, this, &MainWindow::refreshAll);
    topbarLayout->addWidget(refresh);

    rootLayout->addWidget(topbar);

    pages_ = new QStackedWidget(root);
    pages_->setObjectName("contentStack");
    pages_->addWidget(buildBatteryPage());
    pages_->addWidget(buildThermalPage());
    pages_->addWidget(buildSaverPage());
    connect(
        navigation_,
        &QTabBar::currentChanged,
        pages_,
        &QStackedWidget::setCurrentIndex
    );
    navigation_->setCurrentIndex(0);

    rootLayout->addWidget(pages_, 1);
    setCentralWidget(root);
}

QWidget* MainWindow::buildBatteryPage() {
    auto* content = new QWidget;
    auto* layout = new QVBoxLayout(content);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(18);

    layout->addWidget(
        pageHeader(
            QStringLiteral("Battery"),
            QStringLiteral(
                "Firmware charging policy and native capability status."
            ),
            content
        )
    );

    auto* statusStrip = surface(content);
    statusStrip->setObjectName("statusStrip");
    auto* statusLayout = new QHBoxLayout(statusStrip);
    statusLayout->setContentsMargins(0, 0, 0, 0);
    statusLayout->setSpacing(0);

    statusLayout->addWidget(
        statBlock(
            QStringLiteral("Battery interface"),
            batteryName_,
            QStringLiteral("Kernel device used for charging control."),
            statusStrip
        ),
        1
    );
    statusLayout->addWidget(verticalDivider(statusStrip));
    statusLayout->addWidget(
        statBlock(
            QStringLiteral("Firmware mode"),
            chargeMode_,
            QStringLiteral("Current charging policy exposed by firmware."),
            statusStrip
        ),
        1
    );
    statusLayout->addWidget(verticalDivider(statusStrip));
    statusLayout->addWidget(
        statBlock(
            QStringLiteral("Thresholds"),
            chargeInterval_,
            QStringLiteral("Custom charge start and stop window."),
            statusStrip
        ),
        1
    );
    layout->addWidget(statusStrip);

    layout->addWidget(
        sectionHeader(
            QStringLiteral("Charge control"),
            QStringLiteral(
                "Only capabilities advertised by the native daemon can be changed."
            ),
            content
        )
    );

    auto* controlSurface = surface(content);
    auto* controlLayout = new QVBoxLayout(controlSurface);
    controlLayout->setContentsMargins(20, 18, 20, 18);
    controlLayout->setSpacing(14);

    auto* supportRow = new QHBoxLayout;
    auto* supportCopy = new QWidget(controlSurface);
    auto* supportCopyLayout = new QVBoxLayout(supportCopy);
    supportCopyLayout->setContentsMargins(0, 0, 0, 0);
    supportCopyLayout->setSpacing(3);

    auto* supportTitle = new QLabel(
        QStringLiteral("Dell firmware interface"),
        supportCopy
    );
    supportTitle->setObjectName("settingTitle");
    supportCopyLayout->addWidget(supportTitle);

    auto* supportSubtitle = new QLabel(
        QStringLiteral(
            "PowerDeck never exposes write controls that the kernel cannot verify."
        ),
        supportCopy
    );
    supportSubtitle->setObjectName("mutedText");
    supportSubtitle->setWordWrap(true);
    supportCopyLayout->addWidget(supportSubtitle);

    supportRow->addWidget(supportCopy, 1);
    chargeSupport_ = new QLabel(QStringLiteral("Checking…"), controlSurface);
    chargeSupport_->setObjectName("statePill");
    supportRow->addWidget(chargeSupport_, 0, Qt::AlignVCenter);
    controlLayout->addLayout(supportRow);
    controlLayout->addWidget(divider(controlSurface));

    chargeModeSelect_ = new QComboBox(controlSurface);
    chargeModeSelect_->setMinimumWidth(220);

    applyChargeModeButton_ = new QPushButton(
        QStringLiteral("Apply mode"),
        controlSurface
    );
    applyChargeModeButton_->setObjectName("primaryButton");
    connect(
        applyChargeModeButton_,
        &QPushButton::clicked,
        this,
        &MainWindow::applyChargeMode
    );

    auto* modeActions = new QWidget(controlSurface);
    auto* modeActionsLayout = new QHBoxLayout(modeActions);
    modeActionsLayout->setContentsMargins(0, 0, 0, 0);
    modeActionsLayout->setSpacing(8);
    modeActionsLayout->addWidget(chargeModeSelect_);
    modeActionsLayout->addWidget(applyChargeModeButton_);

    controlLayout->addWidget(
        settingRow(
            QStringLiteral("Charging mode"),
            QStringLiteral(
                "Choose the firmware policy used while AC power is connected."
            ),
            modeActions,
            controlSurface
        )
    );

    auto* chargeModeHelp = new QLabel(
        chargingModeDescription(QString()),
        controlSurface
    );
    chargeModeHelp->setObjectName("mutedText");
    chargeModeHelp->setWordWrap(true);
    controlLayout->addWidget(chargeModeHelp);

    connect(
        chargeModeSelect_,
        &QComboBox::currentTextChanged,
        this,
        [this, chargeModeHelp](const QString& mode) {
            chargeModeHelp->setText(chargingModeDescription(mode));
            const auto current = chargeModeSelect_
                                     ->property("powerdeckCurrentMode")
                                     .toString();
            applyChargeModeButton_->setEnabled(
                chargeModeSelect_->isEnabled()
                && !mode.isEmpty()
                && mode != current
            );
        }
    );

    controlLayout->addWidget(divider(controlSurface));

    chargeStart_ = new QSpinBox(controlSurface);
    chargeStart_->setRange(50, 95);
    chargeStart_->setSuffix(QStringLiteral(" %"));
    chargeStart_->setMinimumWidth(92);

    chargeEnd_ = new QSpinBox(controlSurface);
    chargeEnd_->setRange(55, 100);
    chargeEnd_->setSuffix(QStringLiteral(" %"));
    chargeEnd_->setMinimumWidth(92);

    connect(
        chargeStart_,
        static_cast<void (QSpinBox::*)(int)>(&QSpinBox::valueChanged),
        this,
        [this](int start) {
            chargeEnd_->setMinimum(std::max(55, start + 5));
        }
    );

    applyThresholdsButton_ = new QPushButton(
        QStringLiteral("Apply thresholds"),
        controlSurface
    );
    applyThresholdsButton_->setObjectName("primaryButton");
    connect(
        applyThresholdsButton_,
        &QPushButton::clicked,
        this,
        &MainWindow::applyThresholds
    );

    auto* thresholdActions = new QWidget(controlSurface);
    auto* thresholdActionsLayout = new QHBoxLayout(thresholdActions);
    thresholdActionsLayout->setContentsMargins(0, 0, 0, 0);
    thresholdActionsLayout->setSpacing(8);
    thresholdActionsLayout->addWidget(chargeStart_);

    auto* arrow = new QLabel(QStringLiteral("→"), thresholdActions);
    arrow->setObjectName("mutedText");
    thresholdActionsLayout->addWidget(arrow);

    thresholdActionsLayout->addWidget(chargeEnd_);
    thresholdActionsLayout->addWidget(applyThresholdsButton_);

    controlLayout->addWidget(
        settingRow(
            QStringLiteral("Custom thresholds"),
            QStringLiteral(
                "Start charging below the first value and stop at the second."
            ),
            thresholdActions,
            controlSurface
        )
    );

    const auto updateThresholdApplyState = [this]() {
        const bool available = applyThresholdsButton_
                                   ->property("powerdeckThresholdsAvailable")
                                   .toBool();
        const int start = chargeStart_->value();
        const int end = chargeEnd_->value();
        const int currentStart = chargeStart_
                                     ->property("powerdeckCurrentValue")
                                     .toInt();
        const int currentEnd = chargeEnd_
                                   ->property("powerdeckCurrentValue")
                                   .toInt();
        const bool valid = end - start >= 5;
        const bool changed = start != currentStart || end != currentEnd;
        applyThresholdsButton_->setEnabled(available && valid && changed);
    };
    connect(
        chargeStart_,
        static_cast<void (QSpinBox::*)(int)>(&QSpinBox::valueChanged),
        this,
        [updateThresholdApplyState](int) { updateThresholdApplyState(); }
    );
    connect(
        chargeEnd_,
        static_cast<void (QSpinBox::*)(int)>(&QSpinBox::valueChanged),
        this,
        [updateThresholdApplyState](int) { updateThresholdApplyState(); }
    );

    chargeControlNote_ = new QLabel(
        QStringLiteral("Checking hardware support…"),
        controlSurface
    );
    chargeControlNote_->setObjectName("inlineNote");
    chargeControlNote_->setWordWrap(true);
    controlLayout->addWidget(chargeControlNote_);

    layout->addWidget(controlSurface);
    layout->addStretch();
    return scrollPage(content);
}

QWidget* MainWindow::buildThermalPage() {
    auto* content = new QWidget;
    auto* layout = new QVBoxLayout(content);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(18);

    layout->addWidget(
        pageHeader(
            QStringLiteral("Thermal"),
            QStringLiteral(
                "Live package power, GPU activity and firmware-managed cooling."
            ),
            content
        )
    );

    auto* telemetryStrip = surface(content);
    telemetryStrip->setObjectName("telemetryStrip");
    auto* telemetryLayout = new QHBoxLayout(telemetryStrip);
    telemetryLayout->setContentsMargins(0, 0, 0, 0);
    telemetryLayout->setSpacing(0);

    telemetryLayout->addWidget(
        statBlock(
            QStringLiteral("CPU package"),
            cpuWatts_,
            QStringLiteral("Intel RAPL package power."),
            telemetryStrip
        ),
        1
    );
    telemetryLayout->addWidget(verticalDivider(telemetryStrip));
    telemetryLayout->addWidget(
        statBlock(
            QStringLiteral("GPU"),
            gpuWatts_,
            QStringLiteral("DRM hwmon or Linux perf energy."),
            telemetryStrip
        ),
        1
    );
    telemetryLayout->addWidget(verticalDivider(telemetryStrip));
    telemetryLayout->addWidget(
        statBlock(
            QStringLiteral("Fan"),
            fanRpm_,
            QStringLiteral("Read-only RPM from hwmon."),
            telemetryStrip
        ),
        1
    );
    layout->addWidget(telemetryStrip);

    layout->addWidget(
        sectionHeader(
            QStringLiteral("Cooling profile"),
            QStringLiteral(
                "Request a verified platform profile while firmware keeps fan safety."
            ),
            content
        )
    );

    auto* profileSurface = surface(content);
    auto* profileLayout = new QGridLayout(profileSurface);
    profileLayout->setContentsMargins(20, 18, 20, 18);
    profileLayout->setHorizontalSpacing(28);
    profileLayout->setVerticalSpacing(12);

    auto* currentTitle = new QLabel(
        QStringLiteral("Current profile"),
        profileSurface
    );
    currentTitle->setObjectName("settingTitle");
    profileLayout->addWidget(currentTitle, 0, 0);

    auto* requestedTitle = new QLabel(
        QStringLiteral("Requested profile"),
        profileSurface
    );
    requestedTitle->setObjectName("settingTitle");
    profileLayout->addWidget(requestedTitle, 0, 1);

    thermalCurrent_ = new QLabel(QStringLiteral("Loading…"), profileSurface);
    thermalCurrent_->setObjectName("profileValue");
    profileLayout->addWidget(thermalCurrent_, 1, 0);

    auto* requestedActions = new QWidget(profileSurface);
    auto* requestedLayout = new QHBoxLayout(requestedActions);
    requestedLayout->setContentsMargins(0, 0, 0, 0);
    requestedLayout->setSpacing(8);

    thermalSelect_ = new QComboBox(requestedActions);
    thermalSelect_->setMinimumWidth(220);
    requestedLayout->addWidget(thermalSelect_, 1);

    applyThermalButton_ = new QPushButton(
        QStringLiteral("Apply profile"),
        requestedActions
    );
    applyThermalButton_->setObjectName("primaryButton");
    connect(
        applyThermalButton_,
        &QPushButton::clicked,
        this,
        &MainWindow::applyThermalProfile
    );
    requestedLayout->addWidget(applyThermalButton_);
    profileLayout->addWidget(requestedActions, 1, 1);

    thermalSource_ = new QLabel(QStringLiteral("Loading source…"), profileSurface);
    thermalSource_->setObjectName("mutedText");
    thermalSource_->setWordWrap(true);
    profileLayout->addWidget(thermalSource_, 2, 0);

    auto* requestedHint = new QLabel(
        QStringLiteral(
            "Apply is disabled when the selected profile already matches."
        ),
        profileSurface
    );
    requestedHint->setObjectName("mutedText");
    requestedHint->setWordWrap(true);
    profileLayout->addWidget(requestedHint, 2, 1);

    auto* thermalModeHelp = new QLabel(
        thermalProfileDescription(QString()),
        profileSurface
    );
    thermalModeHelp->setObjectName("inlineNote");
    thermalModeHelp->setWordWrap(true);
    profileLayout->addWidget(thermalModeHelp, 3, 0, 1, 2);

    profileLayout->setColumnStretch(0, 1);
    profileLayout->setColumnStretch(1, 1);

    connect(
        thermalSelect_,
        &QComboBox::currentTextChanged,
        this,
        [this, thermalModeHelp](const QString& profile) {
            thermalModeHelp->setText(thermalProfileDescription(profile));
            applyThermalButton_->setEnabled(
                !profile.isEmpty() && profile != thermalCurrent_->text()
            );
        }
    );

    layout->addWidget(profileSurface);

    auto* note = new QLabel(
        QStringLiteral(
            "PowerDeck changes only kernel-advertised platform profiles. "
            "It never writes raw fan PWM."
        ),
        content
    );
    note->setObjectName("inlineNote");
    note->setWordWrap(true);
    layout->addWidget(note);

    layout->addStretch();
    return scrollPage(content);
}

QWidget* MainWindow::buildSaverPage() {
    auto* content = new QWidget;
    auto* layout = new QVBoxLayout(content);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(18);

    layout->addWidget(
        pageHeader(
            QStringLiteral("Battery Saver"),
            QStringLiteral(
                "A native policy that coordinates display, CPU and device savings."
            ),
            content
        )
    );

    auto* masterSurface = surface(content);
    masterSurface->setObjectName("masterSurface");
    auto* masterLayout = new QHBoxLayout(masterSurface);
    masterLayout->setContentsMargins(22, 18, 22, 18);
    masterLayout->setSpacing(18);

    auto* masterCopy = new QWidget(masterSurface);
    auto* masterCopyLayout = new QVBoxLayout(masterCopy);
    masterCopyLayout->setContentsMargins(0, 0, 0, 0);
    masterCopyLayout->setSpacing(4);

    auto* masterTitle = new QLabel(
        QStringLiteral("Battery Saver runtime"),
        masterCopy
    );
    masterTitle->setObjectName("masterTitle");
    masterCopyLayout->addWidget(masterTitle);

    auto* masterSubtitle = new QLabel(
        QStringLiteral(
            "Turn the policy on now, or let the native agent activate it on battery."
        ),
        masterCopy
    );
    masterSubtitle->setObjectName("mutedText");
    masterSubtitle->setWordWrap(true);
    masterCopyLayout->addWidget(masterSubtitle);
    masterLayout->addWidget(masterCopy, 1);

    saverState_ = new QLabel(QStringLiteral("Loading…"), masterSurface);
    saverState_->setObjectName("statePill");
    masterLayout->addWidget(saverState_, 0, Qt::AlignVCenter);

    saverEnabled_ = new SwitchCheckBox(
        QStringLiteral("Enable"),
        masterSurface
    );
    saverEnabled_->setObjectName("masterToggle");
    connect(saverEnabled_, &QCheckBox::toggled, this, [this](bool enabled) {
        if (!saverRefresh_) {
            setSaverEnabled(enabled);
        }
    });
    masterLayout->addWidget(saverEnabled_, 0, Qt::AlignVCenter);
    layout->addWidget(masterSurface);

    layout->addWidget(
        sectionHeader(
            QStringLiteral("Automation"),
            QStringLiteral(
                "The user agent reacts to AC transitions even when this window is closed."
            ),
            content
        )
    );

    auto* automationSurface = surface(content);
    auto* automationLayout = new QVBoxLayout(automationSurface);
    automationLayout->setContentsMargins(20, 16, 20, 16);
    automationLayout->setSpacing(12);

    automationEnabled_ = new SwitchCheckBox(QString(), automationSurface);
    autoOnBattery_ = new SwitchCheckBox(QString(), automationSurface);
    restoreOnAc_ = new SwitchCheckBox(QString(), automationSurface);

    automationLayout->addWidget(
        settingRow(
            QStringLiteral("Automatic Battery Saver"),
            QStringLiteral("Allow automatic sessions based on AC state."),
            automationEnabled_,
            automationSurface
        )
    );
    automationLayout->addWidget(divider(automationSurface));
    automationLayout->addWidget(
        settingRow(
            QStringLiteral("Enable when unplugged"),
            QStringLiteral("Start a saver session when battery power begins."),
            autoOnBattery_,
            automationSurface
        )
    );
    automationLayout->addWidget(divider(automationSurface));
    automationLayout->addWidget(
        settingRow(
            QStringLiteral("Restore on AC"),
            QStringLiteral("Restore only values still owned by that saver session."),
            restoreOnAc_,
            automationSurface
        )
    );
    layout->addWidget(automationSurface);

    layout->addWidget(
        sectionHeader(
            QStringLiteral("Policy"),
            QStringLiteral("These values are applied together when Saver becomes active."),
            content
        )
    );

    auto* policyGrid = new QGridLayout;
    policyGrid->setContentsMargins(0, 0, 0, 0);
    policyGrid->setHorizontalSpacing(14);
    policyGrid->setVerticalSpacing(14);

    auto* displaySurface = surface(content);
    auto* displayLayout = new QVBoxLayout(displaySurface);
    displayLayout->setContentsMargins(20, 18, 20, 18);
    displayLayout->setSpacing(12);

    auto* displayTitle = new QLabel(QStringLiteral("Display"), displaySurface);
    displayTitle->setObjectName("panelTitle");
    displayLayout->addWidget(displayTitle);

    brightnessCap_ = new QSpinBox(displaySurface);
    brightnessCap_->setRange(1, 100);
    brightnessCap_->setSuffix(QStringLiteral(" %"));
    brightnessCap_->setMinimumWidth(104);

    onlyLowerBrightness_ = new SwitchCheckBox(QString(), displaySurface);

    targetRefreshRate_ = new QDoubleSpinBox(displaySurface);
    targetRefreshRate_->setRange(1.0, 1000.0);
    targetRefreshRate_->setDecimals(3);
    targetRefreshRate_->setSuffix(QStringLiteral(" Hz"));
    targetRefreshRate_->setMinimumWidth(124);

    displayLayout->addWidget(
        settingRow(
            QStringLiteral("Brightness cap"),
            QStringLiteral("Maximum brightness while Saver owns the display."),
            brightnessCap_,
            displaySurface
        )
    );
    displayLayout->addWidget(divider(displaySurface));
    displayLayout->addWidget(
        settingRow(
            QStringLiteral("Only lower brightness"),
            QStringLiteral("Never raise brightness above the current value."),
            onlyLowerBrightness_,
            displaySurface
        )
    );
    displayLayout->addWidget(divider(displaySurface));
    displayLayout->addWidget(
        settingRow(
            QStringLiteral("Target refresh rate"),
            QStringLiteral("Nearest same-resolution internal display mode."),
            targetRefreshRate_,
            displaySurface
        )
    );

    auto* performanceSurface = surface(content);
    auto* performanceLayout = new QVBoxLayout(performanceSurface);
    performanceLayout->setContentsMargins(20, 18, 20, 18);
    performanceLayout->setSpacing(12);

    auto* performanceTitle = new QLabel(
        QStringLiteral("Performance"),
        performanceSurface
    );
    performanceTitle->setObjectName("panelTitle");
    performanceLayout->addWidget(performanceTitle);

    saverPowerProfile_ = new QComboBox(performanceSurface);
    saverPowerProfile_->addItems({
        QStringLiteral("power-saver"),
        QStringLiteral("balanced"),
        QStringLiteral("performance"),
    });
    saverPowerProfile_->setMinimumWidth(160);

    saverThermal_ = new QComboBox(performanceSurface);
    saverThermal_->addItems({
        QStringLiteral("quiet"),
        QStringLiteral("cool"),
        QStringLiteral("balanced"),
        QStringLiteral("performance"),
    });
    saverThermal_->setMinimumWidth(160);

    disableTurbo_ = new SwitchCheckBox(QString(), performanceSurface);

    maxPerformance_ = new QSpinBox(performanceSurface);
    maxPerformance_->setRange(1, 100);
    maxPerformance_->setSuffix(QStringLiteral(" %"));
    maxPerformance_->setMinimumWidth(104);

    performanceLayout->addWidget(
        settingRow(
            QStringLiteral("OS power profile"),
            QStringLiteral("System power profile while Saver is active."),
            saverPowerProfile_,
            performanceSurface
        )
    );
    performanceLayout->addWidget(divider(performanceSurface));
    performanceLayout->addWidget(
        settingRow(
            QStringLiteral("Thermal profile"),
            QStringLiteral("Firmware profile requested during a saver session."),
            saverThermal_,
            performanceSurface
        )
    );

    auto* saverThermalHelp = new QLabel(
        thermalProfileDescription(saverThermal_->currentText()),
        performanceSurface
    );
    saverThermalHelp->setObjectName("mutedText");
    saverThermalHelp->setWordWrap(true);
    performanceLayout->addWidget(saverThermalHelp);
    connect(
        saverThermal_,
        &QComboBox::currentTextChanged,
        this,
        [saverThermalHelp](const QString& profile) {
            saverThermalHelp->setText(thermalProfileDescription(profile));
        }
    );

    performanceLayout->addWidget(divider(performanceSurface));
    performanceLayout->addWidget(
        settingRow(
            QStringLiteral("Disable CPU turbo"),
            QStringLiteral("Prevent Intel turbo boost while Saver is active."),
            disableTurbo_,
            performanceSurface
        )
    );
    performanceLayout->addWidget(divider(performanceSurface));
    performanceLayout->addWidget(
        settingRow(
            QStringLiteral("Maximum CPU performance"),
            QStringLiteral("Intel P-state maximum performance percentage."),
            maxPerformance_,
            performanceSurface
        )
    );

    policyGrid->addWidget(displaySurface, 0, 0);
    policyGrid->addWidget(performanceSurface, 0, 1);
    policyGrid->setColumnStretch(0, 1);
    policyGrid->setColumnStretch(1, 1);
    layout->addLayout(policyGrid);

    auto* devicesSurface = surface(content);
    auto* devicesLayout = new QVBoxLayout(devicesSurface);
    devicesLayout->setContentsMargins(20, 18, 20, 18);
    devicesLayout->setSpacing(12);

    auto* devicesTitle = new QLabel(QStringLiteral("Devices"), devicesSurface);
    devicesTitle->setObjectName("panelTitle");
    devicesLayout->addWidget(devicesTitle);

    keyboardBacklight_ = new QSpinBox(devicesSurface);
    keyboardBacklight_->setRange(0, 100);
    keyboardBacklight_->setMinimumWidth(104);

    muteAudio_ = new SwitchCheckBox(QString(), devicesSurface);

    devicesLayout->addWidget(
        settingRow(
            QStringLiteral("Keyboard backlight"),
            QStringLiteral("Backlight level used by the saver session."),
            keyboardBacklight_,
            devicesSurface
        )
    );
    devicesLayout->addWidget(divider(devicesSurface));
    devicesLayout->addWidget(
        settingRow(
            QStringLiteral("Mute audio"),
            QStringLiteral("Mute the default output while Saver is active."),
            muteAudio_,
            devicesSurface
        )
    );
    layout->addWidget(devicesSurface);

    auto* saveRow = new QFrame(content);
    saveRow->setObjectName("saveRow");
    auto* saveLayout = new QHBoxLayout(saveRow);
    saveLayout->setContentsMargins(0, 4, 0, 4);
    saveLayout->setSpacing(16);

    auto* saveCopy = new QLabel(
        QStringLiteral(
            "Settings are stored by the native agent and reused for manual "
            "and automatic sessions."
        ),
        saveRow
    );
    saveCopy->setObjectName("mutedText");
    saveCopy->setWordWrap(true);
    saveLayout->addWidget(saveCopy, 1);

    auto* saveButton = new QPushButton(
        QStringLiteral("Save Battery Saver settings"),
        saveRow
    );
    saveButton->setObjectName("primaryButton");
    connect(
        saveButton,
        &QPushButton::clicked,
        this,
        &MainWindow::saveSaverSettings
    );
    saveLayout->addWidget(saveButton, 0, Qt::AlignVCenter);

    layout->addWidget(saveRow);
    layout->addStretch();
    return scrollPage(content);
}

void MainWindow::installStyle() {
    setStyleSheet(QStringLiteral(R"(
        QMainWindow, #appRoot, #pageShell {
            background: #070c0f;
            color: #e7edf5;
        }

        #contentStack, #pageScroll {
            background: transparent;
        }

        #topbar {
            background: #10161a;
            border: 1px solid #2b3941;
            border-radius: 12px;
        }

        #brandMark {
            background: #8fd9ea;
            color: #081216;
            border-radius: 9px;
            font-weight: 900;
        }

        #appTitle {
            color: #f2f4f7;
            font-size: 17px;
            font-weight: 750;
        }

        #brandSubtitle {
            color: #8e99a2;
            font-size: 11px;
        }

        #mainTabs {
            background: transparent;
        }

        QTabBar::tab {
            min-height: 32px;
            padding: 0 14px;
            margin: 0 2px;
            color: #98a4ad;
            background: transparent;
            border: 1px solid transparent;
            border-radius: 8px;
        }

        QTabBar::tab:hover {
            color: #e1e5eb;
            background: #1a2024;
        }

        QTabBar::tab:selected {
            color: #f2f4f7;
            background: #202a30;
            border-color: #37515b;
            font-weight: 650;
        }

        #connectionStatus {
            color: #9fd9b5;
            background: #132117;
            border: 1px solid #2d5a3c;
            border-radius: 9px;
            padding: 5px 9px;
            font-size: 11px;
            font-weight: 650;
        }

        #pageTitle {
            color: #f2f4f7;
            font-size: 30px;
            font-weight: 750;
        }

        #pageSubtitle {
            color: #97a4ad;
            font-size: 13px;
        }

        #sectionTitle {
            color: #e6e9ee;
            font-size: 16px;
            font-weight: 700;
        }

        #panelTitle {
            color: #edf0f4;
            font-size: 15px;
            font-weight: 700;
            padding-bottom: 2px;
        }

        #masterTitle {
            color: #f2f4f7;
            font-size: 18px;
            font-weight: 720;
        }

        #settingTitle {
            color: #dfe3e8;
            font-weight: 650;
        }

        #mutedText, #statDescription {
            color: #97a4ad;
        }

        #statLabel {
            color: #99a7b0;
            font-size: 12px;
            font-weight: 650;
        }

        #statValue {
            color: #f2f4f7;
            font-size: 25px;
            font-weight: 760;
        }

        #surface, #statusStrip, #telemetryStrip, #masterSurface {
            background: #1a2024;
            border: 1px solid #2d3a42;
            border-radius: 12px;
        }

        #masterSurface {
            border-left: 3px solid #8fd9ea;
        }

        #divider, #verticalDivider {
            background: #2d3a42;
            border: none;
        }

        #statePill {
            color: #dfe7ec;
            background: #1a2126;
            border: 1px solid #546a76;
            border-radius: 10px;
            padding: 5px 10px;
            font-size: 11px;
            font-weight: 650;
        }

        #profileValue {
            color: #f2f4f7;
            font-size: 24px;
            font-weight: 740;
        }

        #inlineNote {
            color: #9aa2ad;
            background: #151b1f;
            border-left: 3px solid #62b7cb;
            padding: 9px 11px;
        }

        #saveRow {
            background: transparent;
            border-top: 1px solid #2d3a42;
        }

        QPushButton {
            min-height: 32px;
            color: #dfe4eb;
            background: #1a2126;
            border: 1px solid #546a76;
            border-radius: 8px;
            padding: 5px 12px;
        }

        QPushButton:hover {
            background: #202a30;
            border-color: #62717a;
        }

        QPushButton#toolbarButton {
            background: transparent;
            border-color: transparent;
            color: #c4c9d1;
        }

        QPushButton#toolbarButton:hover {
            background: #1a2126;
            border-color: #313741;
        }

        QPushButton#primaryButton {
            color: #081216;
            background: #8fd9ea;
            border-color: #8fd9ea;
            font-weight: 700;
        }

        QPushButton#primaryButton:hover {
            background: #9ed8e7;
            border-color: #9ed8e7;
        }

        QPushButton:disabled {
            color: #697882;
            background: #151b1f;
            border-color: #3a4a53;
        }

        QPushButton#primaryButton:disabled {
            color: #72818a;
            background: #2b383e;
            border-color: #2b383e;
        }

        QComboBox, QSpinBox, QDoubleSpinBox {
            min-height: 32px;
            color: #e0e4eb;
            background: #12181c;
            border: 1px solid #38515b;
            border-radius: 8px;
            padding: 3px 8px;
            selection-background-color: #24424d;
        }

        QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
            border-color: #8fd9ea;
        }

        QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {
            color: #687883;
            background: #12181c;
            border-color: #39474f;
        }

        QCheckBox {
            color: #dfe4eb;
            spacing: 8px;
            background: transparent;
            border: none;
            padding: 0;
        }

        QScrollArea {
            border: none;
            background: transparent;
        }

        QScrollBar:vertical {
            width: 11px;
            background: transparent;
            margin: 3px 0;
        }

        QScrollBar::handle:vertical {
            min-height: 36px;
            background: #343b45;
            border-radius: 5px;
        }

        QScrollBar::handle:vertical:hover {
            background: #4a5160;
        }

        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical,
        QScrollBar::add-page:vertical,
        QScrollBar::sub-page:vertical {
            height: 0;
            background: transparent;
        }
    )"));
}

void MainWindow::callJson(
    bool systemBus,
    const QString& service,
    const QString& path,
    const QString& interfaceName,
    const QString& member,
    const QVariantList& arguments,
    JsonCallback callback
) {
    const auto connection = systemBus
        ? QDBusConnection::systemBus()
        : QDBusConnection::sessionBus();
    auto* dbusInterface = new QDBusInterface(
        service,
        path,
        interfaceName,
        connection,
        this
    );
    if (!dbusInterface->isValid()) {
        showError(dbusInterface->lastError().message());
        dbusInterface->deleteLater();
        return;
    }

    auto* watcher = new QDBusPendingCallWatcher(
        dbusInterface->asyncCallWithArgumentList(member, arguments),
        this
    );
    connect(
        watcher,
        &QDBusPendingCallWatcher::finished,
        this,
        [this, watcher, dbusInterface, callback = std::move(callback)]() {
            const QDBusPendingReply<QString> reply = *watcher;
            watcher->deleteLater();
            dbusInterface->deleteLater();
            if (reply.isError()) {
                showError(reply.error().message());
                return;
            }
            QJsonParseError error;
            const auto document = QJsonDocument::fromJson(
                reply.value().toUtf8(),
                &error
            );
            if (error.error != QJsonParseError::NoError || !document.isObject()) {
                showError(
                    QStringLiteral("Malformed JSON reply: ") + error.errorString()
                );
                return;
            }
            callback(document.object());
        }
    );
}

void MainWindow::showError(const QString& text) {
    statusLabel_->setText(
        QStringLiteral("Error · ") + humanDbusError(text)
    );
    statusLabel_->setToolTip(text);
}

void MainWindow::showStatus(const QString& text) {
    statusLabel_->setText(text);
    statusLabel_->setToolTip(QString());
}

void MainWindow::refreshAll() {
    showStatus(QStringLiteral("Connected"));
    refreshBattery();
    refreshThermal();
    refreshTelemetry();
    refreshSaver();
    refreshSaverSettings();
}

void MainWindow::refreshBattery() {
    callJson(
        true,
        kSystemService,
        kSystemPath,
        kSystemInterface,
        QStringLiteral("GetChargeState"),
        {},
        [this](const QJsonObject& state) {
            batteryName_->setText(
                optionalString(state, QStringLiteral("battery_name"))
            );

            const auto current = optionalString(
                state,
                QStringLiteral("current_mode")
            );
            chargeMode_->setText(current);

            chargeModeSelect_->clear();
            bool customAvailable = false;
            const auto modes = state
                                   .value(QStringLiteral("available_modes"))
                                   .toArray();
            for (const auto& value : modes) {
                if (!value.isString()) {
                    continue;
                }
                const auto mode = value.toString();
                chargeModeSelect_->addItem(mode);
                if (mode.compare(
                        QStringLiteral("custom"),
                        Qt::CaseInsensitive
                    ) == 0) {
                    customAvailable = true;
                }
            }

            const bool supported = !modes.isEmpty();
            chargeSupport_->setText(
                supported
                    ? QStringLiteral("Available")
                    : QStringLiteral("Unavailable")
            );
            chargeModeSelect_->setEnabled(supported);

            const auto modeIndex = chargeModeSelect_->findText(current);
            if (modeIndex >= 0) {
                chargeModeSelect_->setCurrentIndex(modeIndex);
            }

            chargeModeSelect_->setProperty(
                "powerdeckCurrentMode",
                current
            );
            applyChargeModeButton_->setEnabled(
                supported
                && !chargeModeSelect_->currentText().isEmpty()
                && chargeModeSelect_->currentText() != current
            );

            const auto interval = state
                                      .value(QStringLiteral("interval"))
                                      .toObject();
            const bool thresholdsAvailable = customAvailable && !interval.isEmpty();
            if (thresholdsAvailable) {
                const auto start = interval
                                       .value(QStringLiteral("start_percent"))
                                       .toInt();
                const auto end = interval
                                     .value(QStringLiteral("end_percent"))
                                     .toInt();
                chargeStart_->setProperty("powerdeckCurrentValue", start);
                chargeEnd_->setProperty("powerdeckCurrentValue", end);
                chargeStart_->setValue(start);
                chargeEnd_->setMinimum(std::max(55, start + 5));
                chargeEnd_->setValue(end);
                chargeInterval_->setText(
                    QStringLiteral("%1–%2 %").arg(start).arg(end)
                );
            } else {
                chargeStart_->setProperty("powerdeckCurrentValue", -1);
                chargeEnd_->setProperty("powerdeckCurrentValue", -1);
                chargeInterval_->setText(QStringLiteral("Unavailable"));
            }

            applyThresholdsButton_->setProperty(
                "powerdeckThresholdsAvailable",
                thresholdsAvailable
            );
            chargeStart_->setEnabled(thresholdsAvailable);
            chargeEnd_->setEnabled(thresholdsAvailable);
            applyThresholdsButton_->setEnabled(false);

            if (!supported) {
                chargeControlNote_->setText(
                    QStringLiteral(
                        "Dell charging controls are not exposed by the native "
                        "daemon on this machine. Read-only battery information "
                        "remains available."
                    )
                );
            } else if (!customAvailable) {
                chargeControlNote_->setText(
                    QStringLiteral(
                        "Charging modes are available, but this firmware does "
                        "not advertise Custom mode."
                    )
                );
            } else if (!thresholdsAvailable) {
                chargeControlNote_->setText(
                    QStringLiteral(
                        "Custom mode is advertised, but the kernel does not expose "
                        "verified start/stop threshold controls."
                    )
                );
            } else {
                chargeControlNote_->setText(
                    QStringLiteral(
                        "Writes are verified after every change. A mismatched "
                        "write is rolled back by the native daemon."
                    )
                );
            }
        }
    );
}

void MainWindow::refreshThermal() {
    callJson(
        true,
        kSystemService,
        kSystemPath,
        kSystemInterface,
        QStringLiteral("GetThermalState"),
        {},
        [this](const QJsonObject& state) {
            const auto current = optionalString(
                state,
                QStringLiteral("current_profile")
            );
            thermalCurrent_->setText(current);
            thermalSource_->setText(
                QStringLiteral("Source: %1").arg(
                    optionalString(state, QStringLiteral("source"))
                )
            );

            thermalSelect_->clear();
            for (const auto& value :
                 state.value(QStringLiteral("available_profiles")).toArray()) {
                if (value.isString()) {
                    thermalSelect_->addItem(value.toString());
                }
            }

            const auto index = thermalSelect_->findText(current);
            if (index >= 0) {
                thermalSelect_->setCurrentIndex(index);
            }
            applyThermalButton_->setEnabled(
                !thermalSelect_->currentText().isEmpty()
                && thermalSelect_->currentText() != current
            );
        }
    );
}

void MainWindow::refreshTelemetry() {
    if (telemetryPending_) {
        return;
    }
    telemetryPending_ = true;
    callJson(
        true,
        kSystemService,
        kSystemPath,
        kSystemInterface,
        QStringLiteral("GetTelemetryState"),
        {},
        [this](const QJsonObject& state) {
            telemetryPending_ = false;
            cpuWatts_->setText(wattsText(state.value(QStringLiteral("cpu_watts"))));
            gpuWatts_->setText(wattsText(state.value(QStringLiteral("gpu_watts"))));
            const auto fan = state.value(QStringLiteral("fan_rpm"));
            fanRpm_->setText(
                fan.isDouble()
                    ? QString::number(fan.toInteger()) + QStringLiteral(" RPM")
                    : QStringLiteral("Firmware managed")
            );
        }
    );
    QTimer::singleShot(2000, this, [this]() { telemetryPending_ = false; });
}

void MainWindow::refreshSaver() {
    callJson(
        false,
        kAgentService,
        kAgentPath,
        kAgentInterface,
        QStringLiteral("GetState"),
        {},
        [this](const QJsonObject& state) {
            saverRefresh_ = true;
            const auto enabled = state.value(QStringLiteral("enabled")).toBool();
            saverEnabled_->setChecked(enabled);
            saverRefresh_ = false;

            const auto automatic = state
                                       .value(QStringLiteral("automatic_session"))
                                       .toBool();
            const auto acValue = state.value(QStringLiteral("on_ac_power"));
            QString acText = QStringLiteral("unknown");
            if (acValue.isBool()) {
                acText = acValue.toBool()
                    ? QStringLiteral("online")
                    : QStringLiteral("offline");
            }
            saverState_->setText(
                QStringLiteral("%1 · AC %2%3")
                    .arg(enabled ? QStringLiteral("Active") : QStringLiteral("Inactive"))
                    .arg(acText)
                    .arg(automatic ? QStringLiteral(" · automatic") : QString())
            );
        }
    );
}

void MainWindow::refreshSaverSettings() {
    callJson(
        false,
        kAgentService,
        kAgentPath,
        kAgentInterface,
        QStringLiteral("GetSettings"),
        {},
        [this](const QJsonObject& settings) {
            automationEnabled_->setChecked(
                settings.value(QStringLiteral("enabled")).toBool(true)
            );
            autoOnBattery_->setChecked(
                settings.value(QStringLiteral("auto_enable_on_battery")).toBool(true)
            );
            restoreOnAc_->setChecked(
                settings.value(QStringLiteral("restore_on_ac")).toBool(true)
            );
            brightnessCap_->setValue(
                settings.value(QStringLiteral("brightness_cap_percent")).toInt(40)
            );
            onlyLowerBrightness_->setChecked(
                settings.value(QStringLiteral("only_lower_brightness")).toBool(true)
            );
            targetRefreshRate_->setValue(
                settings.value(QStringLiteral("target_refresh_rate_hz")).toDouble(60.0)
            );

            const auto power = settings
                                   .value(QStringLiteral("power_profile"))
                                   .toString(QStringLiteral("power-saver"));
            const auto powerIndex = saverPowerProfile_->findText(power);
            if (powerIndex >= 0) {
                saverPowerProfile_->setCurrentIndex(powerIndex);
            }

            const auto thermal = settings
                                     .value(QStringLiteral("thermal_profile"))
                                     .toString(QStringLiteral("quiet"));
            const auto thermalIndex = saverThermal_->findText(thermal);
            if (thermalIndex >= 0) {
                saverThermal_->setCurrentIndex(thermalIndex);
            }

            disableTurbo_->setChecked(
                settings.value(QStringLiteral("disable_turbo")).toBool(true)
            );
            maxPerformance_->setValue(
                settings.value(QStringLiteral("max_performance_percent")).toInt(60)
            );
            keyboardBacklight_->setValue(
                settings.value(QStringLiteral("keyboard_backlight_level")).toInt(0)
            );
            muteAudio_->setChecked(
                settings.value(QStringLiteral("mute_audio")).toBool(false)
            );
        }
    );
}

void MainWindow::applyChargeMode() {
    const auto mode = chargeModeSelect_->currentText();
    if (mode.isEmpty()) {
        return;
    }
    callJson(
        true,
        kSystemService,
        kSystemPath,
        kSystemInterface,
        QStringLiteral("SetChargeMode"),
        {mode},
        [this](const QJsonObject&) {
            showStatus(QStringLiteral("Charging mode applied and verified."));
            refreshBattery();
        }
    );
}

void MainWindow::applyThresholds() {
    if (chargeEnd_->value() - chargeStart_->value() < 5) {
        showError(
            QStringLiteral(
                "Custom charge end must be at least 5% above the start threshold."
            )
        );
        return;
    }
    callJson(
        true,
        kSystemService,
        kSystemPath,
        kSystemInterface,
        QStringLiteral("SetChargeThresholds"),
        {chargeStart_->value(), chargeEnd_->value()},
        [this](const QJsonObject&) {
            showStatus(QStringLiteral("Custom thresholds applied and verified."));
            refreshBattery();
        }
    );
}

void MainWindow::applyThermalProfile() {
    const auto profile = thermalSelect_->currentText();
    if (profile.isEmpty()) {
        return;
    }
    callJson(
        true,
        kSystemService,
        kSystemPath,
        kSystemInterface,
        QStringLiteral("SetThermalProfile"),
        {profile},
        [this](const QJsonObject&) {
            showStatus(QStringLiteral("Thermal profile applied and verified."));
            refreshThermal();
        }
    );
}

void MainWindow::setSaverEnabled(bool enabled) {
    callJson(
        false,
        kAgentService,
        kAgentPath,
        kAgentInterface,
        QStringLiteral("SetSaverEnabled"),
        {enabled},
        [this](const QJsonObject&) {
            showStatus(QStringLiteral("Battery Saver state updated."));
            refreshSaver();
        }
    );
}

void MainWindow::saveSaverSettings() {
    QJsonObject settings;
    settings.insert(QStringLiteral("enabled"), automationEnabled_->isChecked());
    settings.insert(
        QStringLiteral("auto_enable_on_battery"),
        autoOnBattery_->isChecked()
    );
    settings.insert(QStringLiteral("restore_on_ac"), restoreOnAc_->isChecked());
    settings.insert(
        QStringLiteral("brightness_cap_percent"),
        brightnessCap_->value()
    );
    settings.insert(
        QStringLiteral("only_lower_brightness"),
        onlyLowerBrightness_->isChecked()
    );
    settings.insert(
        QStringLiteral("target_refresh_rate_hz"),
        targetRefreshRate_->value()
    );
    settings.insert(
        QStringLiteral("power_profile"),
        saverPowerProfile_->currentText()
    );
    settings.insert(
        QStringLiteral("thermal_profile"),
        saverThermal_->currentText()
    );
    settings.insert(QStringLiteral("disable_turbo"), disableTurbo_->isChecked());
    settings.insert(
        QStringLiteral("max_performance_percent"),
        maxPerformance_->value()
    );
    settings.insert(
        QStringLiteral("keyboard_backlight_level"),
        keyboardBacklight_->value()
    );
    settings.insert(QStringLiteral("mute_audio"), muteAudio_->isChecked());

    const auto payload = QString::fromUtf8(
        QJsonDocument(settings).toJson(QJsonDocument::Compact)
    );
    callJson(
        false,
        kAgentService,
        kAgentPath,
        kAgentInterface,
        QStringLiteral("SetSettings"),
        {payload},
        [this](const QJsonObject&) {
            showStatus(QStringLiteral("Battery Saver settings saved."));
            refreshSaverSettings();
        }
    );
}
