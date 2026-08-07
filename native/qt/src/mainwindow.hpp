#pragma once

#include <functional>

#include <QJsonObject>
#include <QMainWindow>
#include <QVariantList>

class QCheckBox;
class QComboBox;
class QDoubleSpinBox;
class QLabel;
class QTabBar;
class QPushButton;
class QSpinBox;
class QStackedWidget;
class QTimer;

class MainWindow final : public QMainWindow {
    Q_OBJECT

public:
    explicit MainWindow(QWidget* parent = nullptr);

private:
    using JsonCallback = std::function<void(const QJsonObject&)>;

    void buildUi();
    QWidget* buildBatteryPage();
    QWidget* buildThermalPage();
    QWidget* buildSaverPage();
    void installStyle();

    void callJson(
        bool systemBus,
        const QString& service,
        const QString& path,
        const QString& interfaceName,
        const QString& member,
        const QVariantList& arguments,
        JsonCallback callback
    );
    void showError(const QString& text);
    void showStatus(const QString& text);

    void refreshAll();
    void refreshBattery();
    void refreshThermal();
    void refreshTelemetry();
    void refreshSaver();
    void refreshSaverSettings();

    void applyChargeMode();
    void applyThresholds();
    void applyThermalProfile();
    void setSaverEnabled(bool enabled);
    void saveSaverSettings();

    QTabBar* navigation_ = nullptr;
    QStackedWidget* pages_ = nullptr;
    QLabel* statusLabel_ = nullptr;

    QLabel* batteryName_ = nullptr;
    QLabel* chargeMode_ = nullptr;
    QLabel* chargeInterval_ = nullptr;
    QLabel* chargeSupport_ = nullptr;
    QLabel* chargeControlNote_ = nullptr;
    QComboBox* chargeModeSelect_ = nullptr;
    QSpinBox* chargeStart_ = nullptr;
    QSpinBox* chargeEnd_ = nullptr;
    QPushButton* applyChargeModeButton_ = nullptr;
    QPushButton* applyThresholdsButton_ = nullptr;

    QLabel* thermalCurrent_ = nullptr;
    QLabel* thermalSource_ = nullptr;
    QComboBox* thermalSelect_ = nullptr;
    QPushButton* applyThermalButton_ = nullptr;
    QLabel* cpuWatts_ = nullptr;
    QLabel* gpuWatts_ = nullptr;
    QLabel* fanRpm_ = nullptr;

    QCheckBox* saverEnabled_ = nullptr;
    QCheckBox* automationEnabled_ = nullptr;
    QCheckBox* autoOnBattery_ = nullptr;
    QCheckBox* restoreOnAc_ = nullptr;
    QSpinBox* brightnessCap_ = nullptr;
    QCheckBox* onlyLowerBrightness_ = nullptr;
    QDoubleSpinBox* targetRefreshRate_ = nullptr;
    QComboBox* saverPowerProfile_ = nullptr;
    QComboBox* saverThermal_ = nullptr;
    QCheckBox* disableTurbo_ = nullptr;
    QSpinBox* maxPerformance_ = nullptr;
    QSpinBox* keyboardBacklight_ = nullptr;
    QCheckBox* muteAudio_ = nullptr;
    QLabel* saverState_ = nullptr;

    QTimer* telemetryTimer_ = nullptr;
    bool telemetryPending_ = false;
    bool saverRefresh_ = false;
};
