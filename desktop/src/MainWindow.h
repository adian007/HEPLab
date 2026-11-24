#pragma once

#include <QMainWindow>
#include <QJsonObject>
#include <QJsonArray>
#include "EventData.h"
#include "ProjectStore.h"
#include <memory>

class QStackedWidget;
class QLabel;
class QAction;
class QComboBox;
class QSpinBox;
class QDoubleSpinBox;
class QPushButton;
class QTextEdit;
class QTextBrowser;
class QTimer;
class QListWidget;
class QLineEdit;
class QCheckBox;
class DetectorViewport3D;
class EventProjectionWidget;
class ScientificPlotWidget;
class QTableWidget;

class WorkerClient;
class QProgressBar;

namespace heplab {

class OpenDataWorkspace;
class LearningWorkspace;

class MainWindow : public QMainWindow {
    Q_OBJECT

public:
    explicit MainWindow(QWidget* parent = nullptr, const QString& projectsDirectory = {});
    ~MainWindow() override;

public slots:
    void setInspectorEvent(const QJsonObject& event);

private:
    void buildCommandBar();
    void buildStatusBar();
    QString findRepositoryRoot() const;
    void buildHomePage(QWidget* page);
    void refreshProjectList();
    void renderRunHistory();
    void filterRunHistory();
    void createProject();
    void openSelectedProject();
    void renameSelectedProject();
    void saveActiveProject();
    QJsonObject simulationConfig() const;
    int completedEventCount() const;
    void refreshRunHistory();
    void buildEventInspectorPage(QWidget* page);
    void buildRunsPage(QWidget* page);
    void refreshComparisonAxes();
    void refreshCutflow();
    void refreshBinTable();
    void clearInspectorEvent(const QString& message);
    void selectInspectorObject(int objectId);
    void refreshInspectorViews();
    void previousInspectorEvent();
    void nextInspectorEvent();
    void buildSimulationPage(QWidget* page);
    void startSimulationRun();
    void cancelCurrentRun();
    void saveCommittedResult();
    void pollCurrentRun();
    void handleWorkerResponse(int requestId, const QJsonObject& response);
    void handleWorkerHandshake(const QJsonObject& handshake);

    QStackedWidget* pages_ = nullptr;
    QListWidget* navigation_ = nullptr;
    QLabel* activeProjectLabel_ = nullptr;
    QTextBrowser* validationSummary_ = nullptr;
    QTextBrowser* resultSummary_ = nullptr;
    QTextEdit* validationView_ = nullptr;
    QLabel* statusLabel_ = nullptr;
    QComboBox* experiment_ = nullptr;
    QComboBox* particleSource_ = nullptr;
    QSpinBox* seed_ = nullptr;
    QSpinBox* eventBudget_ = nullptr;
    QDoubleSpinBox* muonPtCut_ = nullptr;
    QDoubleSpinBox* muonEtaCut_ = nullptr;
    QDoubleSpinBox* muonIsoCut_ = nullptr;
    QDoubleSpinBox* momentum_ = nullptr;
    QDoubleSpinBox* field_ = nullptr;
    QDoubleSpinBox* thickness_ = nullptr;
    QPushButton* runButton_ = nullptr;
    QPushButton* stopButton_ = nullptr;
    QPushButton* saveButton_ = nullptr;
    QTextEdit* resultView_ = nullptr;
    QTimer* pollTimer_ = nullptr;
    std::unique_ptr<WorkerClient> worker_;
    std::unique_ptr<ProjectStore> projects_;
    QListWidget* projectList_ = nullptr;
    QLineEdit* projectName_ = nullptr;
    QTableWidget* runList_ = nullptr;
    QLineEdit* historyFilter_ = nullptr;
    QJsonArray runHistory_;
    bool sortHistoryById_ = false;
    OpenDataWorkspace* openData_ = nullptr;
    LearningWorkspace* learning_ = nullptr;
    QProgressBar* progress_ = nullptr;
    EventProjectionWidget* xyProjection_ = nullptr;
    EventProjectionWidget* xzProjection_ = nullptr;
    QMainWindow* inspectorDockHost_ = nullptr;
    DetectorViewport3D* detector3D_ = nullptr;
    heplab::EventData currentEventData_;
    QPushButton* reset3DButton_ = nullptr;
    QTableWidget* geometryTable_ = nullptr;
    QTableWidget* particleTable_ = nullptr;
    QTextEdit* propertyInspector_ = nullptr;
    QPushButton* previousEventButton_ = nullptr;
    QPushButton* nextEventButton_ = nullptr;
    QLabel* eventIndexLabel_ = nullptr;
    QLabel* eventSummaryLabel_ = nullptr;
    QComboBox* trajectoryFilter_ = nullptr;
    QAction* trajectoryFilterAction_ = nullptr;
    QPushButton* frameTrackButton_ = nullptr;
    QWidget* comparisonPanel_ = nullptr;
    QLabel* comparisonTitle_ = nullptr;
    QPushButton* compareButton_ = nullptr;
    ScientificPlotWidget* comparisonPlot_ = nullptr;
    ScientificPlotWidget* scientificPlot_ = nullptr;
    QComboBox* plotObservable_ = nullptr;
    QTableWidget* binTable_ = nullptr;
    QLabel* binTableStatus_ = nullptr;
    QTableWidget* cutflowTable_ = nullptr;
    QLabel* cutflowStatus_ = nullptr;
    QJsonObject pinnedResult_;
    bool sharedManualRange_ = false;
    int inspectorEventIndex_ = 0;
    QString projectRoot_;
    QString currentRunId_;
    int submitRequestId_ = -1;
    int pollRequestId_ = -1;
    int eventRequestId_ = -1;
    int runHistoryRequestId_ = -1;
    int evidenceRequestId_ = -1;
    int datasetListRequestId_ = -1;
    QJsonObject completedJob_;
    QJsonObject completedEvent_;
};

} // namespace heplab
