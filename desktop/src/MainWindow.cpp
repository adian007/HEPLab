#include "MainWindow.h"
#include <QDockWidget>
#include <QGridLayout>
#include <QSlider>
#include <QToolButton>
#include <QWidgetAction>
#include "EventProjectionWidget.h"
#include <QTextBrowser>
#include <QTabWidget>
#include "WorkbenchTheme.h"
#include "ResearchCatalogs.h"
#include <QToolBar>
#include <QSettings>
#include <QInputDialog>
#include <QGroupBox>
#include <QProgressBar>
#include <QSaveFile>
#include <QHeaderView>
#include <QFontDatabase>
#include <QScrollArea>
#include <QMenuBar>
#include <QDesktopServices>
#include <QMenu>
#include <QUrl>
#include <algorithm>
#include <cmath>
#include <utility>
#include "WorkerClient.h"

#include <QComboBox>
#include <QCheckBox>
#include <QCoreApplication>
#include <QDir>
#include <QDoubleSpinBox>
#include <QFile>
#include <QFileDialog>
#include <QFormLayout>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QPushButton>
#include <QSpinBox>
#include <QSplitter>
#include <QStackedWidget>
#include <QStandardPaths>
#include <QStatusBar>
#include <QSignalBlocker>
#include <QShortcut>
#include <QTextBrowser>
#include <QTabWidget>
#include <QTextEdit>
#include <QTextDocument>
#include <QTimer>
#include <QVBoxLayout>
#include <QDateTime>
#include <QUuid>
#include <QCryptographicHash>
#include <QTableWidget>
#include "DetectorViewport3D.h"
#include "ScientificPlotWidget.h"

namespace heplab {

namespace {
QString evidenceNumber(const QJsonObject& record, const QString& key, double scale = 1.0)
{
    const auto value = record.value(key);
    return value.isDouble() ? QString::number(value.toDouble() * scale, 'g', 6)
                            : QStringLiteral("Unavailable");
}

QString validationReport(const QJsonObject& evidence)
{
    const auto silicon = evidence.value("silicon").toObject();
    const auto field = evidence.value("cms_field").toObject();
    QUrl reference(silicon.value("source_url").toString());
    if (reference.scheme() != "https") reference = QUrl();
    const QString status = field.value("passed").isBool()
        ? (field.value("passed").toBool() ? "PASS" : "FAIL") : "UNAVAILABLE";
    return QString(
        "<h2>Numerical verification</h2>"
        "<h3>CMS tracker field · %1</h3><p>%2</p>"
        "<table cellspacing='8'><tr><td>Model</td><td>%3</td></tr>"
        "<tr><td>Maximum vector residual [T]</td><td>%4</td></tr>"
        "<tr><td>RMS vector residual [T]</td><td>%5</td></tr>"
        "<tr><td>Maximum permitted residual [T]</td><td>%6</td></tr>"
        "<tr><td>Tracker reference rows</td><td>%7</td></tr></table>"
        "<h3>Silicon energy loss · %8</h3><p>%9</p>"
        "<p>Maximum held-out relative error: %10%. "
        "<a href='%11'>Reference data</a></p>")
        .arg(status, field.value("scope").toString().toHtmlEscaped(),
             field.value("model").toString().toHtmlEscaped(),
             evidenceNumber(field, "max_vector_error_t"),
             evidenceNumber(field, "rms_vector_error_t"),
             evidenceNumber(field, "gate_max_vector_error_t"),
             evidenceNumber(field, "tracker_rows"),
             silicon.value("status").toString("Unavailable").toHtmlEscaped(),
             silicon.value("scope").toString().toHtmlEscaped(),
             evidenceNumber(silicon, "max_abs_relative_error", 100.0),
             reference.toString(QUrl::FullyEncoded).toHtmlEscaped());
}

void addTechnicalDetails(QVBoxLayout* layout, QTextEdit* viewer)
{
    auto* toggle = new QCheckBox("Show technical JSON", viewer->parentWidget());
    viewer->hide();
    QObject::connect(toggle, &QCheckBox::toggled, viewer, &QWidget::setVisible);
    layout->addWidget(toggle, 0, Qt::AlignLeft);
    layout->addWidget(viewer, 1);
}

QString pdgSpeciesName(int pdgId, const QString& collection)
{
    if (pdgId == 0 && !collection.isEmpty()) return collection;
    switch (pdgId) {
    case 11: return QStringLiteral("e⁻ (11)");
    case -11: return QStringLiteral("e⁺ (-11)");
    case 12: return QStringLiteral("νₑ (12)");
    case -12: return QStringLiteral("ν̄ₑ (-12)");
    case 13: return QStringLiteral("μ⁻ (13)");
    case -13: return QStringLiteral("μ⁺ (-13)");
    case 14: return QStringLiteral("ν_μ (14)");
    case -14: return QStringLiteral("ν̄_μ (-14)");
    case 22: return QStringLiteral("γ (22)");
    case 111: return QStringLiteral("π⁰ (111)");
    case 211: return QStringLiteral("π⁺ (211)");
    case -211: return QStringLiteral("π⁻ (-211)");
    case 130: return QStringLiteral("K⁰_L (130)");
    case 310: return QStringLiteral("K⁰_S (310)");
    case 321: return QStringLiteral("K⁺ (321)");
    case -321: return QStringLiteral("K⁻ (-321)");
    case 2112: return QStringLiteral("n (2112)");
    case -2112: return QStringLiteral("n̄ (-2112)");
    case 2212: return QStringLiteral("p (2212)");
    case -2212: return QStringLiteral("p̄ (-2212)");
    default: return QString::number(pdgId);
    }
}

QString formatEventOverviewHtml(const QJsonObject& event, const heplab::EventData& data, int trackCount)
{
    const bool collision = event.value("mode").toString() == "pythia";
    const auto info = event.value("event_info").toObject();
    const auto config = event.value("config").toObject();
    const auto artifact = event.value("artifact").toObject();
    QString html = QStringLiteral("<h3 style='margin:0 0 8px'>Event overview</h3>");
    html += QStringLiteral("<p style='margin:0 0 8px'>%1 objects  ·  %2 displayed trajectories  ·  %3 model surfaces</p>")
        .arg(data.tracks.size()).arg(trackCount).arg(data.detectorSurfaces.size());
    if (collision || !info.isEmpty()) {
        const bool selected = info.value("selected").toBool(false);
        const QString selectionText = info.contains("selected")
            ? (selected ? QStringLiteral("Selected dimuon") : QStringLiteral("Not selected"))
            : QStringLiteral("Unavailable");
        const auto massVal = info.value("mass_gev");
        const QString massText = massVal.isDouble()
            ? QString::number(massVal.toDouble(), 'g', 5) + QStringLiteral(" GeV/c²")
            : QStringLiteral("n/a");
        const auto metVal = info.value("met_gev");
        const QString metText = metVal.isDouble()
            ? QString::number(metVal.toDouble(), 'g', 4) + QStringLiteral(" GeV/c")
            : QStringLiteral("n/a");
        html += QStringLiteral(
            "<table cellspacing='4' style='margin:4px 0 8px'>"
            "<tr><td><b>Source</b></td><td>%1</td></tr>"
            "<tr><td><b>Weight</b></td><td>%2</td></tr>"
            "<tr><td><b>Selection</b></td><td>%3</td></tr>"
            "<tr><td><b>Dimuon mass</b></td><td>%4</td></tr>"
            "<tr><td><b>Missing pT</b></td><td>%5</td></tr>"
            "<tr><td><b>DELPHES muons / jets</b></td><td>%6 / %7</td></tr>")
            .arg(collision ? QStringLiteral("PYTHIA8 / DELPHES 13 TeV DY → μμ")
                           : event.value("mode").toString("analytic").toHtmlEscaped(),
                 evidenceNumber(info, "weight"),
                 selectionText.toHtmlEscaped(),
                 massText.toHtmlEscaped(),
                 metText.toHtmlEscaped(),
                 info.value("muons").isDouble() ? QString::number(info.value("muons").toInteger()) : QStringLiteral("n/a"),
                 info.value("jets").isDouble() ? QString::number(info.value("jets").toInteger()) : QStringLiteral("n/a"));
        if (!artifact.value("run_id").toString().isEmpty()) {
            html += QStringLiteral("<tr><td><b>Run ID</b></td><td>%1</td></tr>")
                .arg(artifact.value("run_id").toString().left(16).toHtmlEscaped());
        }
        if (config.value("seed").isDouble()) {
            html += QStringLiteral("<tr><td><b>Seed</b></td><td>%1</td></tr>")
                .arg(config.value("seed").toInteger());
        }
        html += QStringLiteral("</table>");
    }
    const QString displayNote = event.value("display").toString();
    if (!displayNote.isEmpty()) {
        html += QStringLiteral("<p style='margin:6px 0'>%1</p>").arg(displayNote.toHtmlEscaped());
    }
    html += QStringLiteral(
        "<p style='margin:6px 0 0; opacity:0.85'>Select a trajectory in any view or choose a row in Event objects. "
        "Generator truth particles, DELPHES reconstructed objects, and ideal-solenoid display paths are distinct; "
        "crossings are predictions, not measured hits.</p>");
    return html;
}
} // namespace


MainWindow::MainWindow(QWidget* parent, const QString& projectsDirectory)
    : QMainWindow(parent)
{
    setWindowTitle("HEPLab Workbench");
    setWindowIcon(QIcon(QStringLiteral(":/branding/heplab-logo.png")));
    const QSettings preferences;
    applyWorkbenchTheme(preferences.value("appearance/dark", true).toBool(),
                        preferences.value("appearance/compact", false).toBool());
    resize(1280, 820);

    projects_ = std::make_unique<ProjectStore>(projectsDirectory);
    projectRoot_ = projects_->activeProjectRoot();
    if (projectRoot_.isEmpty()) {
        const QString activeId = projects_->createProject("Default Project");
        if (!activeId.isEmpty()) {
            projectRoot_ = projects_->activeProjectRoot();
        }
    }

    auto* center = new QWidget(this);
    auto* shellLayout = new QHBoxLayout(center);
    shellLayout->setContentsMargins(0, 0, 0, 0);
    shellLayout->setSpacing(0);
    auto* rail = new QWidget(center);
    rail->setObjectName("workspaceRail");
    rail->setFixedWidth(176);
    auto* railLayout = new QVBoxLayout(rail);
    railLayout->setContentsMargins(10, 12, 10, 10);
    auto* brandRow = new QHBoxLayout();
    brandRow->setContentsMargins(4, 4, 4, 12);
    brandRow->setSpacing(8);
    auto* logo = new QLabel(rail);
    const QPixmap logoPix(QStringLiteral(":/branding/heplab-logo.png"));
    if (!logoPix.isNull()) {
        logo->setPixmap(logoPix.scaled(28, 28, Qt::KeepAspectRatio, Qt::SmoothTransformation));
    }
    logo->setFixedSize(28, 28);
    auto* brand = new QLabel("HEPLab", rail);
    brand->setObjectName("workspaceBrand");
    brandRow->addWidget(logo);
    brandRow->addWidget(brand, 1);
    railLayout->addLayout(brandRow);
    navigation_ = new QListWidget(rail);
    navigation_->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    navigation_->setTextElideMode(Qt::ElideRight);
    railLayout->addWidget(navigation_, 1);
    navigation_->setObjectName("mainNavigation");
    navigation_->setAccessibleName("Scientific workspaces");
    navigation_->addItems({
        "Home / Projects",
        "Simulation",
        "Event Inspector",
        "CMS Open Data",
        "Runs / Comparisons",
        "Validation",
        "Learning / Documentation",
    });

    pages_ = new QStackedWidget(center);
    const QStringList titles = {
        "HEPLab Projects",
        "Simulation",
        "Event Inspector",
        "CMS Open Data",
        "Runs and Comparisons",
        "Validation",
        "Learning and Documentation",
    };
    for (const auto& title : titles) {
        auto* page = new QWidget(pages_);
        auto* layout = new QVBoxLayout(page);
        layout->setContentsMargins(18, 12, 18, 12);
        layout->setSpacing(10);
        auto* heading = new QLabel(title, page);
        QFont headingFont = heading->font();
        headingFont.setPointSize(18);
        headingFont.setBold(true);
        heading->setFont(headingFont);
        heading->setWordWrap(true);
        heading->setProperty("workspaceTitle", true);
        if (title == "Event Inspector") {
            heading->hide();
            layout->setContentsMargins(0, 0, 0, 0);
        } else {
            layout->addWidget(heading);
        }
        if (title == "HEPLab Projects") {
            buildHomePage(page);
        } else if (title == "Simulation") {
            buildSimulationPage(page);
        } else if (title == "Event Inspector") {
            buildEventInspectorPage(page);
        } else if (title == "Runs and Comparisons") {
            buildRunsPage(page);
        } else if (title == "CMS Open Data") {
            openData_ = new OpenDataWorkspace(page);
            layout->addWidget(openData_, 1);
        } else if (title == "Learning and Documentation") {
            learning_ = new LearningWorkspace(page);
            layout->addWidget(learning_, 1);
        } else {
            validationView_ = new QTextEdit(page);
            validationView_->setReadOnly(true);
            validationView_->setPlaceholderText("Waiting for the worker's validation evidence.");
            validationSummary_ = new QTextBrowser(page);
            validationSummary_->setObjectName("validationReport");
            validationSummary_->setOpenExternalLinks(true);
            validationSummary_->setPlainText("Waiting for validation data from the local worker.");
            layout->addWidget(validationSummary_, 2);
            addTechnicalDetails(layout, validationView_);
        }
        pages_->addWidget(page);
    }

    connect(navigation_, &QListWidget::currentRowChanged,
            pages_, &QStackedWidget::setCurrentIndex);
    navigation_->setCurrentRow(0);
    pages_->setCurrentIndex(0);
    shellLayout->addWidget(rail);
    shellLayout->addWidget(pages_, 1);
    setCentralWidget(center);
    buildStatusBar();
    buildCommandBar();
    restoreGeometry(preferences.value("workspace/window").toByteArray());

    if (qEnvironmentVariableIsEmpty("HEPLAB_DISABLE_WORKER_FOR_TESTS")) {
        worker_ = std::make_unique<WorkerClient>(this);
        connect(worker_.get(), &WorkerClient::handshakeReceived,
                this, &MainWindow::handleWorkerHandshake);
        connect(worker_.get(), &WorkerClient::responseReceived,
                this, &MainWindow::handleWorkerResponse);
        connect(worker_.get(), &WorkerClient::workerError,
                this, [this](const QString& message) {
                    statusLabel_->setText(message);
                });
        worker_->start(findRepositoryRoot(), projectRoot_);
    }

    pollTimer_ = new QTimer(this);
    pollTimer_->setInterval(100);
    connect(pollTimer_, &QTimer::timeout, this, &MainWindow::pollCurrentRun);
}

MainWindow::~MainWindow()
{
    QSettings().setValue("workspace/window", saveGeometry());
    if (inspectorDockHost_ && !inspectorDockHost_->property("focusMode").toBool())
        QSettings().setValue("workspace/inspectorDocksV2", inspectorDockHost_->saveState(1));
    if (worker_) {
        worker_->stop();
    }
}

void MainWindow::buildStatusBar()
{
    statusLabel_ = new QLabel("Native shell ready - backend not yet connected");
    statusBar()->addWidget(statusLabel_, 1);
    activeProjectLabel_ = new QLabel(projects_->project(projects_->activeProjectId()).value("name").toString(), this);
    statusBar()->addPermanentWidget(activeProjectLabel_);
    statusBar()->addPermanentWidget(new QLabel("m  ·  GeV/c  ·  T", this));
    progress_ = new QProgressBar(this);
    progress_->setMaximumWidth(150);
    progress_->hide();
    statusBar()->addPermanentWidget(progress_);

}

void MainWindow::buildCommandBar()
{
    auto* bar = addToolBar("Workbench commands");
    bar->setObjectName("workbenchCommands");
    bar->setMovable(false);
    auto* workspaceMenu = menuBar()->addMenu("&Workspace");
    auto* project = workspaceMenu->addAction("Projects");
    project->setShortcut(QKeySequence("Alt+1"));
    connect(project, &QAction::triggered, this, [this] { navigation_->setCurrentRow(0); });
    auto* run = bar->addAction("Run simulation");
    run->setShortcut(QKeySequence("Ctrl+Return"));
    connect(run, &QAction::triggered, runButton_, &QPushButton::click);
    connect(runButton_, &QPushButton::clicked, this, [this] { navigation_->setCurrentRow(1); });
    auto* inspector = workspaceMenu->addAction("Event Inspector");
    inspector->setShortcut(QKeySequence("Alt+3"));
    connect(inspector, &QAction::triggered, this, [this] { navigation_->setCurrentRow(2); });
    auto* commands = bar->addAction("Commands…");
    commands->setShortcut(QKeySequence("Ctrl+K"));
    connect(commands, &QAction::triggered, this, [this] {
        QStringList names;
        for (int row = 0; row < navigation_->count(); ++row)
            names << navigation_->item(row)->text();
        bool accepted = false;
        const auto choice = QInputDialog::getItem(this, "Workbench commands",
            "Open workspace", names, navigation_->currentRow(), true, &accepted);
        const int row = names.indexOf(choice);
        if (accepted && row >= 0) navigation_->setCurrentRow(row);
    });
    auto* view = menuBar()->addMenu("&View");
    for (const auto& entry : {qMakePair("Dark theme", "appearance/dark"),
                             qMakePair("Expert density", "appearance/compact")}) {
        auto* action = view->addAction(entry.first);
        action->setCheckable(true);
        action->setChecked(QSettings().value(entry.second, entry.second == QString("appearance/dark")).toBool());
        connect(action, &QAction::toggled, this, [key = QString(entry.second)](bool enabled) {
            QSettings settings;
            settings.setValue(key, enabled);
            const bool dark = key == "appearance/dark"
                ? enabled : settings.value("appearance/dark", true).toBool();
            const bool compact = key == "appearance/compact"
                ? enabled : settings.value("appearance/compact", false).toBool();
            applyWorkbenchTheme(dark, compact);
        });
    }
}

void MainWindow::buildRunsPage(QWidget* page)
{
    auto* layout = qobject_cast<QVBoxLayout*>(page->layout());
    auto* toolbar = new QWidget(page);
    auto* toolbarLayout = new QHBoxLayout(toolbar);
    plotObservable_ = new QComboBox(toolbar);
    plotObservable_->setObjectName("runObservable");
    plotObservable_->addItems({"Invariant mass", "Muon pT", "Muon η", "Missing pT", "Jet multiplicity"});
    toolbarLayout->addWidget(new QLabel("Observable", toolbar));
    toolbarLayout->addWidget(plotObservable_);
    toolbarLayout->addStretch();

    scientificPlot_ = new ScientificPlotWidget(page);
    auto* bins = new QSpinBox(toolbar);
    bins->setRange(2, 200);
    bins->setValue(24);
    auto* log = new QCheckBox("Log counts", toolbar);
    auto* uncertainties = new QCheckBox("Event uncertainties", toolbar);
    uncertainties->setChecked(true);
    auto* range = new QPushButton("Axis range…", toolbar);
    auto* exportPlot = new QPushButton("Export PNG…", page);
    auto* exportCsv = new QPushButton("Export CSV…", page);
    toolbarLayout->insertWidget(2, new QLabel("Bins", toolbar));
    toolbarLayout->insertWidget(3, bins);
    toolbarLayout->insertWidget(4, log);
    toolbarLayout->insertWidget(5, uncertainties);
    toolbarLayout->insertWidget(6, range);
    scientificPlot_->setBinCount(bins->value());
    connect(bins, &QSpinBox::valueChanged, scientificPlot_, &ScientificPlotWidget::setBinCount);
    connect(log, &QCheckBox::toggled, scientificPlot_, &ScientificPlotWidget::setLogarithmicCounts);
    connect(uncertainties, &QCheckBox::toggled, scientificPlot_, &ScientificPlotWidget::setShowUncertainties);
    connect(range, &QPushButton::clicked, this, [this] {
        bool accepted = false;
        const auto mode = QInputDialog::getItem(this, "Axis range", "Range mode",
            {"Automatic", "Manual"}, 0, false, &accepted);
        if (!accepted) return;
        if (mode == "Automatic") {
            sharedManualRange_ = false;
            refreshComparisonAxes();
            return;
        }
        const auto minimum = QInputDialog::getDouble(this, "Axis range", "Minimum (axis units)", 0, -10000, 10000, 3, &accepted);
        if (!accepted) return;
        const auto maximum = QInputDialog::getDouble(this, "Axis range", "Maximum (axis units)", 100, -10000, 10000, 3, &accepted);
        if (accepted) {
            if (scientificPlot_->setAxisRange(minimum, maximum)) {
                sharedManualRange_ = true;
                comparisonPlot_->setAxisRange(minimum, maximum);
            } else
                statusLabel_->setText("Axis maximum must exceed the minimum.");
        }
    });
    connect(exportPlot, &QPushButton::clicked, this, [this] {
        const auto path = QFileDialog::getSaveFileName(this, "Export plot", "heplab-histogram.png", "PNG (*.png)");
        if (path.isEmpty()) return;
        QSaveFile imageFile(path);
        if (!imageFile.open(QIODevice::WriteOnly) ||
            !scientificPlot_->grab().save(&imageFile, "PNG") || !imageFile.commit())
            statusLabel_->setText("Could not write the plot image.");
        else
            statusLabel_->setText("Plot exported.");
    });
    connect(exportCsv, &QPushButton::clicked, this, [this] {
        const auto rows = scientificPlot_->binRows();
        if (rows.isEmpty()) {
            statusLabel_->setText("No histogram bins to export.");
            return;
        }
        const auto path = QFileDialog::getSaveFileName(this, "Export histogram bins", "heplab-histogram.csv", "CSV (*.csv)");
        if (path.isEmpty()) return;
        QSaveFile csvFile(path);
        if (!csvFile.open(QIODevice::WriteOnly | QIODevice::Text)) {
            statusLabel_->setText("Could not open CSV file for writing.");
            return;
        }
        const QString runId = completedJob_.value("id").toString("unsaved");
        const QString modeName = scientificPlot_->isWeighted()
            ? QStringLiteral("raw signed generator weights (no luminosity scaling)")
            : QStringLiteral("unweighted entries");
        QByteArray out;
        out += QString("# HEPLab histogram export\n# Run ID: %1\n# Observable: %2 (%3)\n# Normalization: %4\n# Entries: %5 (events: %6, underflow: %7, overflow: %8)\n")
            .arg(runId, scientificPlot_->title(), scientificPlot_->units(), modeName)
            .arg(scientificPlot_->entryCount()).arg(scientificPlot_->eventCount())
            .arg(scientificPlot_->underflowCount()).arg(scientificPlot_->overflowCount()).toUtf8();
        out += "bin_low,bin_high,count,uncertainty_event_sumw2,normalized_fraction,normalized_uncertainty,cumulative,cumulative_uncertainty\n";
        for (const auto& r : rows) {
            out += QString("%1,%2,%3,%4,%5,%6,%7,%8\n")
                .arg(r.low, 0, 'g', 8).arg(r.high, 0, 'g', 8)
                .arg(r.count, 0, 'g', 8).arg(r.uncertainty, 0, 'g', 8)
                .arg(r.normalized, 0, 'g', 8).arg(r.normalizedUncertainty, 0, 'g', 8)
                .arg(r.cumulative, 0, 'g', 8).arg(r.cumulativeUncertainty, 0, 'g', 8).toUtf8();
        }
        if (csvFile.write(out) != out.size() || !csvFile.commit()) {
            statusLabel_->setText("Could not write the CSV export.");
        } else {
            statusLabel_->setText("Histogram bins exported to CSV.");
        }
    });
    layout->addWidget(toolbar);
    auto* comparison = new QPushButton("Pin current run", toolbar);
    comparison->setObjectName("pinRun");
    comparison->setEnabled(false);
    auto* unpin = new QPushButton("Clear pin", toolbar);
    unpin->setEnabled(false);
    auto* comparisonActions = new QHBoxLayout;
    comparisonActions->addWidget(comparison);
    comparisonActions->addWidget(unpin);
    comparisonActions->addSpacing(10);
    comparisonActions->addWidget(new QLabel("Graph", page));
    auto* graph = new QComboBox(page);
    graph->setObjectName("runGraphMode");
    graph->addItems({"Histogram bars", "Step histogram", "Normalized shape (unit area)", "Cumulative"});
    comparisonActions->addWidget(graph);
    comparisonActions->addStretch();
    comparisonActions->addWidget(exportPlot);
    comparisonActions->addWidget(exportCsv);
    layout->addLayout(comparisonActions);
    auto* analysisTabs = new QTabWidget(page);
    layout->addWidget(analysisTabs, 1);
    compareButton_ = comparison;
    auto* plots = new QSplitter(Qt::Horizontal, analysisTabs);
    plots->addWidget(scientificPlot_);
    comparisonPanel_ = new QWidget(plots);
    auto* comparisonLayout = new QVBoxLayout(comparisonPanel_);
    comparisonLayout->setContentsMargins(0, 0, 0, 0);
    comparisonTitle_ = new QLabel(comparisonPanel_);
    comparisonTitle_->setTextInteractionFlags(Qt::TextSelectableByMouse);
    comparisonPlot_ = new ScientificPlotWidget(comparisonPanel_);
    comparisonPlot_->setBinCount(bins->value());
    comparisonLayout->addWidget(comparisonTitle_);
    comparisonLayout->addWidget(comparisonPlot_, 1);
    plots->addWidget(comparisonPanel_);
    comparisonPanel_->hide();
    connect(comparison, &QPushButton::clicked, this, [this, unpin] {
        pinnedResult_ = completedJob_.value("result").toObject();
        const QString id = completedJob_.value("id").toString();
        comparisonTitle_->setText("Pinned run " + id.left(12));
        comparisonTitle_->setToolTip(id);
        comparisonPlot_->setResult(pinnedResult_);
        comparisonPanel_->show();
        refreshComparisonAxes();
        refreshCutflow();
        unpin->setEnabled(true);
    });
    connect(unpin, &QPushButton::clicked, this, [this, unpin] {
        pinnedResult_ = {};
        comparisonPanel_->hide();
        comparisonPlot_->setResult({});
        refreshComparisonAxes();
        refreshCutflow();
        unpin->setEnabled(false);
    });
    connect(bins, &QSpinBox::valueChanged, comparisonPlot_, &ScientificPlotWidget::setBinCount);
    connect(log, &QCheckBox::toggled, comparisonPlot_, &ScientificPlotWidget::setLogarithmicCounts);
    connect(uncertainties, &QCheckBox::toggled, comparisonPlot_, &ScientificPlotWidget::setShowUncertainties);
    analysisTabs->addTab(plots, "Distributions");
    auto* cutflowPage = new QWidget(analysisTabs);
    auto* cutflowLayout = new QVBoxLayout(cutflowPage);
    auto* scope = new QLabel("Collision selection, in order. Weighted yields are generator sums with no luminosity scaling.", cutflowPage);
    scope->setWordWrap(true);
    cutflowLayout->addWidget(scope);
    cutflowTable_ = new QTableWidget(cutflowPage);
    cutflowTable_->setObjectName("collisionCutflow");
    cutflowTable_->setColumnCount(7);
    cutflowTable_->setHorizontalHeaderLabels({"Selection", "Events", "Σw", "√Σw²", "Pinned events", "Pinned Σw", "Pinned √Σw²"});
    cutflowTable_->setAlternatingRowColors(true);
    cutflowTable_->setEditTriggers(QAbstractItemView::NoEditTriggers);
    cutflowTable_->verticalHeader()->hide();
    cutflowTable_->horizontalHeader()->setSectionResizeMode(QHeaderView::ResizeToContents);
    cutflowTable_->horizontalHeader()->setSectionResizeMode(0, QHeaderView::Stretch);
    cutflowLayout->addWidget(cutflowTable_, 1);
    cutflowStatus_ = new QLabel(cutflowPage);
    cutflowStatus_->setWordWrap(true);
    cutflowLayout->addWidget(cutflowStatus_);
    analysisTabs->addTab(cutflowPage, "Selection cutflow");

    auto* binPage = new QWidget(analysisTabs);
    auto* binLayout = new QVBoxLayout(binPage);
    binTableStatus_ = new QLabel("Exact histogram bin values from the current artifact.", binPage);
    binTableStatus_->setWordWrap(true);
    binLayout->addWidget(binTableStatus_);
    binTable_ = new QTableWidget(binPage);
    binTable_->setObjectName("runBinTable");
    binTable_->setColumnCount(7);
    binTable_->setHorizontalHeaderLabels({
        "Bin range", "Value", "±√Σw²", "Normalized", "Cumulative", "Pinned value", "Pinned ±√Σw²"});
    binTable_->setAlternatingRowColors(true);
    binTable_->setEditTriggers(QAbstractItemView::NoEditTriggers);
    binTable_->verticalHeader()->hide();
    binTable_->horizontalHeader()->setSectionResizeMode(QHeaderView::ResizeToContents);
    binTable_->horizontalHeader()->setSectionResizeMode(0, QHeaderView::Stretch);
    binLayout->addWidget(binTable_, 1);
    analysisTabs->addTab(binPage, "Bin values");

    refreshCutflow();
    refreshBinTable();

    connect(scientificPlot_, &ScientificPlotWidget::histogramChanged, this, &MainWindow::refreshBinTable);
    connect(comparisonPlot_, &ScientificPlotWidget::histogramChanged, this, &MainWindow::refreshBinTable);
    connect(graph, &QComboBox::currentIndexChanged, this, [this](int index) {
        const auto mode = static_cast<ScientificPlotWidget::GraphMode>(index);
        scientificPlot_->setGraphMode(mode);
        comparisonPlot_->setGraphMode(mode);
    });
    connect(plotObservable_,
            qOverload<int>(&QComboBox::currentIndexChanged),
            this, [this](int index) {
                const auto observable = static_cast<ScientificPlotWidget::Observable>(index);
                scientificPlot_->setObservable(observable);
                comparisonPlot_->setObservable(observable);
                sharedManualRange_ = false;
                refreshComparisonAxes();
            });
}

void MainWindow::refreshComparisonAxes()
{
    if (sharedManualRange_) return;
    if (pinnedResult_.isEmpty()) {
        scientificPlot_->resetAxisRange();
        comparisonPlot_->resetAxisRange();
        return;
    }
    const auto current = scientificPlot_->naturalAxisRange();
    const auto pinned = comparisonPlot_->naturalAxisRange();
    const double low = std::min(current.first, pinned.first);
    const double high = std::max(current.second, pinned.second);
    scientificPlot_->setAxisRange(low, high);
    comparisonPlot_->setAxisRange(low, high);
}

void MainWindow::refreshCutflow()
{
    const auto analysis = [](const QJsonObject& result) { return result.value("analysis").toObject(); };
    const auto current = analysis(completedJob_.value("result").toObject());
    const auto pinned = analysis(pinnedResult_);
    const auto currentRows = current.value("cutflow").toArray();
    const auto pinnedRows = pinned.value("cutflow").toArray();
    QStringList stages;
    for (const auto& rows : {currentRows, pinnedRows}) {
        for (const auto& value : rows) {
            const QString stage = value.toObject().value("stage").toString();
            if (!stages.contains(stage)) stages.append(stage);
        }
    }
    cutflowTable_->clearContents();
    cutflowTable_->setRowCount(stages.size());
    for (int column = 4; column < 7; ++column) cutflowTable_->setColumnHidden(column, pinnedResult_.isEmpty());
    for (qsizetype row = 0; row < stages.size(); ++row)
        cutflowTable_->setItem(row, 0, new QTableWidgetItem(stages.at(row)));
    const auto populate = [&](const QJsonArray& rows, int offset) {
        for (const auto& value : rows) {
            const auto entry = value.toObject();
            const auto row = stages.indexOf(entry.value("stage").toString());
            const QStringList values{QString::number(entry.value("events").toInteger()),
                QString::number(entry.value("sumw").toDouble(), 'g', 6),
                QString::number(std::sqrt(entry.value("sumw2").toDouble()), 'g', 6)};
            for (int column = 0; column < values.size(); ++column) {
                auto* item = new QTableWidgetItem(values.at(column));
                item->setTextAlignment(Qt::AlignRight | Qt::AlignVCenter);
                cutflowTable_->setItem(row, offset + column, item);
            }
        }
    };
    populate(currentRows, 1);
    populate(pinnedRows, 4);
    const auto cuts = [](const QJsonObject& value) {
        const auto selected = value.value("selection").toObject();
        if (selected.isEmpty()) return QString();
        return QString("pT ≥ %1 GeV/c  ·  |η| < %2  ·  isolation ≤ %3  ·  mass [%4, %5) GeV/c²")
            .arg(selected.value("muon_pt_min_gev").toDouble()).arg(selected.value("muon_abs_eta_max").toDouble())
            .arg(selected.value("muon_iso_max").toDouble()).arg(selected.value("mass_min_gev").toDouble())
            .arg(selected.value("mass_max_gev").toDouble());
    };
    QStringList context;
    if (!currentRows.isEmpty()) context << "Current: " + cuts(current);
    if (!pinnedRows.isEmpty()) context << "Pinned: " + cuts(pinned);
    cutflowStatus_->setText(context.isEmpty() ? "Complete or open a collision run to see its selection cutflow."
                                              : context.join('\n'));
}

void MainWindow::refreshBinTable()
{
    if (!binTable_ || !scientificPlot_) return;
    const auto rows = scientificPlot_->binRows();
    const auto pinnedRows = pinnedResult_.isEmpty()
        ? QVector<ScientificPlotWidget::BinRow>{}
        : comparisonPlot_->binRows();
    const bool hasPinned = !pinnedResult_.isEmpty() && pinnedRows.size() == rows.size();
    binTable_->setColumnHidden(5, !hasPinned);
    binTable_->setColumnHidden(6, !hasPinned);
    binTable_->setRowCount(rows.size());
    for (int i = 0; i < rows.size(); ++i) {
        const auto& r = rows.at(i);
        binTable_->setItem(i, 0, new QTableWidgetItem(
            QString("[%1, %2)").arg(r.low, 0, 'g', 4).arg(r.high, 0, 'g', 4)));
        const QStringList vals{
            QString::number(r.count, 'g', 6),
            QString::number(r.uncertainty, 'g', 4),
            QString::number(r.normalized, 'g', 4),
            QString::number(r.cumulative, 'g', 6),
        };
        for (int c = 0; c < vals.size(); ++c) {
            auto* item = new QTableWidgetItem(vals.at(c));
            item->setTextAlignment(Qt::AlignRight | Qt::AlignVCenter);
            binTable_->setItem(i, 1 + c, item);
        }
        if (hasPinned) {
            const auto& p = pinnedRows.at(i);
            auto* pv = new QTableWidgetItem(QString::number(p.count, 'g', 6));
            auto* pu = new QTableWidgetItem(QString::number(p.uncertainty, 'g', 4));
            pv->setTextAlignment(Qt::AlignRight | Qt::AlignVCenter);
            pu->setTextAlignment(Qt::AlignRight | Qt::AlignVCenter);
            binTable_->setItem(i, 5, pv);
            binTable_->setItem(i, 6, pu);
        }
    }
    if (binTableStatus_) {
        binTableStatus_->setText(QString("%1 (%2)  ·  %3 entries (%4 events)  ·  %5 below / %6 above range")
            .arg(scientificPlot_->title(), scientificPlot_->units())
            .arg(scientificPlot_->entryCount()).arg(scientificPlot_->eventCount())
            .arg(scientificPlot_->underflowCount()).arg(scientificPlot_->overflowCount()));
    }
}

void MainWindow::buildEventInspectorPage(QWidget* page)
{
    auto* layout = qobject_cast<QVBoxLayout*>(page->layout());
    auto* workspace = new QMainWindow(page);
    workspace->setWindowFlags(Qt::Widget);
    workspace->setObjectName("inspectorWorkspace");
    workspace->setDockOptions(QMainWindow::AllowNestedDocks | QMainWindow::AllowTabbedDocks);
    inspectorDockHost_ = workspace;
    layout->setContentsMargins(12, 10, 12, 10);
    layout->setSpacing(8);
    auto* title = new QLabel("Event Inspector", page);
    title->setProperty("workspaceTitle", true);
    eventSummaryLabel_ = new QLabel("Run a simulation or open a saved event", page);
    eventSummaryLabel_->setObjectName("eventSummary");
    eventSummaryLabel_->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
    auto* summary = new QHBoxLayout;
    summary->addWidget(title);
    summary->addStretch();
    summary->addWidget(eventSummaryLabel_);
    layout->addLayout(summary);
    layout->addWidget(workspace, 1);

    auto* toolbar = workspace->addToolBar("Event controls");
    toolbar->setObjectName("inspectorControls");
    toolbar->setMovable(false);
    toolbar->setFloatable(false);
    toolbar->setAllowedAreas(Qt::TopToolBarArea);
    auto* viewLayout = new QComboBox(toolbar);
    viewLayout->setObjectName("eventViewLayout");
    viewLayout->setAccessibleName("Event viewport layout");
    viewLayout->addItems({"3D only", "XY only", "XZ only", "Linked views"});
    viewLayout->setToolTip("Choose the 3D view, a projection, or all three linked views");
    auto* camera = new QComboBox(toolbar);
    camera->addItems({"Isometric", "Along Z", "Along Y", "Along X"});
    camera->setAccessibleName("3D camera orientation");
    camera->setToolTip("Align the 3D camera to a coordinate plane");

    previousEventButton_ = new QPushButton("‹", toolbar);
    previousEventButton_->setAccessibleName("Previous event");
    previousEventButton_->setToolTip("Previous event (Alt+Left)");
    nextEventButton_ = new QPushButton("›", toolbar);
    nextEventButton_->setObjectName("nextEvent");
    nextEventButton_->setAccessibleName("Next event");
    nextEventButton_->setToolTip("Next event (Alt+Right)");
    previousEventButton_->setEnabled(false);
    nextEventButton_->setEnabled(false);
    eventIndexLabel_ = new QLabel("Event —", toolbar);
    eventIndexLabel_->setAlignment(Qt::AlignCenter);
    eventIndexLabel_->setMinimumWidth(108);
    toolbar->addWidget(previousEventButton_);
    toolbar->addWidget(eventIndexLabel_);
    toolbar->addWidget(nextEventButton_);
    toolbar->addSeparator();
    toolbar->addWidget(viewLayout);
    toolbar->addWidget(camera);

    reset3DButton_ = new QPushButton("Fit", toolbar);
    reset3DButton_->setToolTip("Fit all event views and reset the 3D camera");
    toolbar->addWidget(reset3DButton_);
    auto* focusCoreButton = new QPushButton("Core", toolbar);
    focusCoreButton->setObjectName("focusCore");
    focusCoreButton->setToolTip("Zoom the 3D view into the inner detector core");
    toolbar->addWidget(focusCoreButton);
    connect(focusCoreButton, &QPushButton::clicked, detector3D_, &DetectorViewport3D::focusCore);
    frameTrackButton_ = new QPushButton("Frame track", toolbar);
    frameTrackButton_->setObjectName("frameSelectedTrack");
    frameTrackButton_->setToolTip("Center the 3D camera on the selected trajectory");
    frameTrackButton_->setEnabled(false);
    toolbar->addWidget(frameTrackButton_);
    auto* display = new QToolButton(toolbar);
    display->setText("Layers");
    display->setPopupMode(QToolButton::InstantPopup);
    auto* displayMenu = new QMenu(display);
    const auto layer = [displayMenu](const QString& name) {
        auto* action = displayMenu->addAction(name);
        action->setCheckable(true);
        action->setChecked(true);
        return action;
    };
    auto* grid = layer("Grid");
    auto* trajectories = layer("Trajectories");
    auto* crossings = layer("Predicted crossings");
    crossings->setToolTip("Show predicted surface intersections on displayed trajectories");
    auto* geometry = layer("Model surfaces");
    geometry->setToolTip("Surfaces supplied by the event model");
    display->setMenu(displayMenu);
    toolbar->addWidget(display);
    trajectoryFilter_ = new QComboBox(toolbar);
    trajectoryFilter_->addItems({"All paths", "Muon paths", "Other charged paths"});
    trajectoryFilter_->setToolTip("Filter rendered generated trajectories. The event object list keeps all objects.");
    trajectoryFilter_->hide();
    trajectoryFilterAction_ = toolbar->addWidget(trajectoryFilter_);
    trajectoryFilterAction_->setVisible(false);
    connect(trajectoryFilter_, &QComboBox::currentIndexChanged, this, [this] {
        refreshInspectorViews();
        selectInspectorObject(-1);
    });

    auto* referenceMenu = displayMenu->addMenu("CMS geometry references");
    const auto addReference = [referenceMenu](const QString& title, const QString& url) {
        auto* action = referenceMenu->addAction(title);
        QObject::connect(action, &QAction::triggered, action, [url] {
            QDesktopServices::openUrl(QUrl(url));
        });
    };
    addReference("Interactive CMS 3D model", "https://opendata.cern/visualise/events/cms");
    addReference("Muon Technical Design Report", "https://cds.cern.ch/record/343814");
    addReference("CMS Run 3 muon system drawings", "https://cms-results.web.cern.ch/cms-results/public-results/publications/PRF-21-001/index.html");
    detector3D_ = new DetectorViewport3D(workspace);
    detector3D_->setObjectName("eventViewport3D");
    auto* cmsControls = new QWidget(page);
    auto* cmsLayout = new QVBoxLayout(cmsControls);
    cmsLayout->setContentsMargins(10, 10, 10, 10);
    auto* cmsNote = new QLabel("CMS iSpy reference overlays. These layers do not change the event model or its predicted crossings.", cmsControls);
    cmsNote->setWordWrap(true);
    cmsLayout->addWidget(cmsNote);
    auto* layerControls = new QWidget(cmsControls);
    auto* layerRow = new QHBoxLayout(layerControls);
    layerRow->setContentsMargins(0, 0, 0, 0);
    cmsLayout->addWidget(layerControls);
    auto* opacityButton = new QToolButton(toolbar);
    opacityButton->setText("Opacity");
    opacityButton->setToolTip("Adjust CMS muon surface opacity by layer");
    opacityButton->setPopupMode(QToolButton::InstantPopup);
    auto* opacityMenu = new QMenu(opacityButton);
    auto* opacityControls = new QWidget(opacityMenu);
    auto* opacityLayout = new QGridLayout(opacityControls);
    opacityLayout->setContentsMargins(12, 8, 12, 8);
    auto* opacityAction = new QWidgetAction(opacityMenu);
    opacityAction->setDefaultWidget(opacityControls);
    opacityMenu->addAction(opacityAction);
    opacityButton->setMenu(opacityMenu);
    const auto muonLayer = [this, layerControls, layerRow, opacityLayout, opacityControls](
            const QString& name, const QString& description,
            DetectorViewport3D::MuonLayer layer, int defaultOpacity) {
        auto* toggle = new QCheckBox(name, layerControls);
        toggle->setToolTip(description + " · CMS iSpy display geometry");
        layerRow->addWidget(toggle);
        connect(toggle, &QCheckBox::toggled, detector3D_, [this, layer](bool shown) {
            detector3D_->setMuonLayerVisible(layer, shown);
        });
        const int row = opacityLayout->rowCount();
        auto* slider = new QSlider(Qt::Horizontal, opacityControls);
        slider->setAccessibleName(name + " opacity");
        slider->setRange(0, 100);
        slider->setMinimumWidth(125);
        slider->setValue(defaultOpacity);
        auto* percent = new QLabel(QString::number(defaultOpacity) + "%", opacityControls);
        percent->setMinimumWidth(percent->fontMetrics().horizontalAdvance("100%"));
        opacityLayout->addWidget(new QLabel(name, opacityControls), row, 0);
        opacityLayout->addWidget(slider, row, 1);
        opacityLayout->addWidget(percent, row, 2);
        detector3D_->setMuonLayerOpacity(layer, defaultOpacity / 100.0f);
        connect(slider, &QSlider::valueChanged, detector3D_, [this, layer, percent](int value) {
            detector3D_->setMuonLayerOpacity(layer, value / 100.0f);
            percent->setText(QString::number(value) + "%");
        });
    };
    muonLayer("DT", "Drift tubes", DetectorViewport3D::MuonLayer::DT, 35);
    muonLayer("CSC", "Cathode strip chambers", DetectorViewport3D::MuonLayer::CSC, 38);
    muonLayer("RPC", "Resistive plate chambers", DetectorViewport3D::MuonLayer::RPC, 16);
    cmsLayout->addWidget(opacityButton);

    auto* cutawayButton = new QToolButton(toolbar);
    cutawayButton->setText("Cutaway");
    cutawayButton->setToolTip("Move an axis-aligned cutting plane through the CMS reference meshes");
    cutawayButton->setPopupMode(QToolButton::InstantPopup);
    auto* cutawayMenu = new QMenu(cutawayButton);
    auto* cutawayControls = new QWidget(cutawayMenu);
    auto* cutawayLayout = new QGridLayout(cutawayControls);
    cutawayLayout->setContentsMargins(12, 8, 12, 8);
    auto* enabled = new QCheckBox("Enable CMS cutaway", cutawayControls);
    auto* axis = new QComboBox(cutawayControls);
    axis->addItems({"X", "Y", "Z"});
    axis->setCurrentIndex(1);
    axis->setAccessibleName("Cutaway axis");
    auto* position = new QSlider(Qt::Horizontal, cutawayControls);
    position->setRange(-120, 120);
    position->setValue(0);
    position->setMinimumWidth(150);
    position->setAccessibleName("Cutaway plane position in tenths of a metre");
    auto* positionLabel = new QLabel("0.0 m", cutawayControls);
    positionLabel->setMinimumWidth(positionLabel->fontMetrics().horizontalAdvance("−12.0 m"));
    auto* reverse = new QCheckBox("Keep higher coordinates", cutawayControls);
    auto* resetPlane = new QPushButton("Center", cutawayControls);
    cutawayLayout->addWidget(enabled, 0, 0, 1, 3);
    cutawayLayout->addWidget(new QLabel("Axis", cutawayControls), 1, 0);
    cutawayLayout->addWidget(axis, 1, 1, 1, 2);
    cutawayLayout->addWidget(new QLabel("Position", cutawayControls), 2, 0);
    cutawayLayout->addWidget(position, 2, 1);
    cutawayLayout->addWidget(positionLabel, 2, 2);
    cutawayLayout->addWidget(reverse, 3, 0, 1, 2);
    cutawayLayout->addWidget(resetPlane, 3, 2);
    auto* cutawayAction = new QWidgetAction(cutawayMenu);
    cutawayAction->setDefaultWidget(cutawayControls);
    cutawayMenu->addAction(cutawayAction);
    cutawayButton->setMenu(cutawayMenu);
    cmsLayout->addWidget(cutawayButton);
    cmsLayout->addStretch();
    const auto updateCutaway = [this, enabled, axis, position, positionLabel, reverse] {
        const float metres = position->value() / 10.0f;
        positionLabel->setText(QString::number(metres, 'f', 1) + " m");
        detector3D_->setMuonCutaway(enabled->isChecked(),
            static_cast<DetectorViewport3D::CutawayAxis>(axis->currentIndex()),
            metres, reverse->isChecked());
    };
    connect(enabled, &QCheckBox::toggled, detector3D_, updateCutaway);
    connect(axis, &QComboBox::currentIndexChanged, detector3D_, updateCutaway);
    connect(position, &QSlider::valueChanged, detector3D_, updateCutaway);
    connect(reverse, &QCheckBox::toggled, detector3D_, updateCutaway);
    connect(resetPlane, &QPushButton::clicked, position, [position] { position->setValue(0); });

    connect(detector3D_, &DetectorViewport3D::muonLayersUnavailable, this, [this](const QString& reason) {
        statusBar()->showMessage(reason, 15000);
    });
    auto* threeDPanel = new QWidget(page);
    auto* threeDLayout = new QVBoxLayout(threeDPanel);
    threeDLayout->setContentsMargins(0, 0, 0, 0);
    threeDLayout->addWidget(detector3D_, 1);

    particleTable_ = new QTableWidget(page);
    particleTable_->setObjectName("eventParticles");
    particleTable_->setColumnCount(7);
    particleTable_->setHorizontalHeaderLabels({
        "Object ID", "Class", "PDG", "Charge [e]", "pT [GeV/c]",
        "Origin", "Status"});
    particleTable_->setEditTriggers(QAbstractItemView::NoEditTriggers);
    particleTable_->setAlternatingRowColors(true);
    particleTable_->setSelectionBehavior(QAbstractItemView::SelectRows);
    particleTable_->setSelectionMode(QAbstractItemView::SingleSelection);
    propertyInspector_ = new QTextEdit(page);
    propertyInspector_->setObjectName("eventProperties");
    propertyInspector_->setReadOnly(true);
    propertyInspector_->document()->setDocumentMargin(12);
    propertyInspector_->setPlaceholderText(
        "Select a particle track or table row to inspect typed properties.");

    particleTable_->setShowGrid(false);
    particleTable_->verticalHeader()->hide();
    for (int column : {1, 5, 6}) particleTable_->setColumnHidden(column, true);
    particleTable_->setHorizontalHeaderLabels({"ID", "Class", "PDG", "q [e]", "pT [GeV/c]", "Origin", "Status"});
    particleTable_->horizontalHeader()->setSectionResizeMode(QHeaderView::ResizeToContents);
    particleTable_->horizontalHeader()->setStretchLastSection(true);
    particleTable_->verticalHeader()->setDefaultSectionSize(25);
    auto* detailTabs = new QTabWidget(workspace);
    detailTabs->setDocumentMode(true);
    detailTabs->addTab(propertyInspector_, "Track");
    connect(particleTable_, &QTableWidget::itemSelectionChanged, detailTabs, [this, detailTabs] {
        if (particleTable_->currentItem() && !particleTable_->selectedItems().isEmpty()) {
            detailTabs->setCurrentWidget(propertyInspector_);
        }
    });
    geometryTable_ = new QTableWidget(detailTabs);
    geometryTable_->setColumnCount(3);
    geometryTable_->setHorizontalHeaderLabels({"Surface", "Shape", "Dimensions [m]"});
    geometryTable_->setEditTriggers(QAbstractItemView::NoEditTriggers);
    geometryTable_->setAlternatingRowColors(true);
    geometryTable_->horizontalHeader()->setStretchLastSection(true);
    detailTabs->addTab(geometryTable_, "Surfaces");
    detailTabs->addTab(cmsControls, "CMS layers");
    const auto dock = [workspace](const QString& title, const QString& name, QWidget* contents) {
        auto* panel = new QDockWidget(title, workspace);
        panel->setObjectName(name);
        panel->setAllowedAreas(Qt::LeftDockWidgetArea | Qt::RightDockWidgetArea | Qt::BottomDockWidgetArea);
        panel->setWidget(contents);
        workspace->addDockWidget(Qt::RightDockWidgetArea, panel);
        return panel;
    };
    auto* particlesDock = dock("Event objects", "inspectorParticlesDock", particleTable_);
    auto* propertiesDock = dock("Object details", "inspectorPropertiesDock", detailTabs);
    workspace->splitDockWidget(particlesDock, propertiesDock, Qt::Vertical);
    displayMenu->addSeparator();
    displayMenu->addAction(particlesDock->toggleViewAction());
    displayMenu->addAction(propertiesDock->toggleViewAction());

    auto* spacer = new QWidget(toolbar);
    spacer->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
    toolbar->addWidget(spacer);
    auto* focus = toolbar->addAction("Focus");
    focus->setObjectName("inspectorFocus");
    focus->setCheckable(true);
    focus->setToolTip("Hide the inspector docks to maximize the viewport");
    focus->setShortcut(QKeySequence("Ctrl+Shift+F"));
    focus->setShortcutContext(Qt::WidgetWithChildrenShortcut);
    workspace->addAction(focus);
    connect(focus, &QAction::toggled, workspace, [workspace, particlesDock, propertiesDock, beforeFocus = QByteArray{}](bool on) mutable {
        if (on) {
            beforeFocus = workspace->saveState(1);
            QSettings().setValue("workspace/inspectorDocksV2", beforeFocus);
            particlesDock->hide();
            propertiesDock->hide();
        } else {
            workspace->restoreState(beforeFocus, 1);
        }
        workspace->setProperty("focusMode", on);
    });
    const QByteArray savedDocks = QSettings().value("workspace/inspectorDocksV2").toByteArray();

    auto* viewports = new QSplitter(Qt::Vertical, workspace);
    workspace->setCentralWidget(viewports);
    viewports->setChildrenCollapsible(false);
    viewports->addWidget(threeDPanel);
    auto* projections = new QSplitter(Qt::Horizontal, viewports);
    projections->setChildrenCollapsible(false);
    xyProjection_ = new EventProjectionWidget(EventProjectionWidget::Projection::XY, projections);
    xzProjection_ = new EventProjectionWidget(EventProjectionWidget::Projection::XZ, projections);
    projections->addWidget(xyProjection_);
    projections->addWidget(xzProjection_);
    viewports->addWidget(projections);
    viewports->setSizes({460, 200});
    viewports->setStretchFactor(0, 3);
    viewports->setStretchFactor(1, 1);
    if (!workspace->restoreState(savedDocks, 1)) {
        workspace->resizeDocks({particlesDock}, {280}, Qt::Horizontal);
        workspace->resizeDocks({particlesDock, propertiesDock}, {175, 350}, Qt::Vertical);
    }
    const auto applyView = [=, this](int index) {
        threeDPanel->setVisible(index == 0 || index == 3);
        projections->setVisible(index != 0);
        xyProjection_->setVisible(index == 1 || index == 3);
        xzProjection_->setVisible(index == 2 || index == 3);
        camera->setEnabled(index == 0 || index == 3);
        frameTrackButton_->setVisible(camera->isEnabled());
    };
    connect(viewLayout, &QComboBox::currentIndexChanged, page, applyView);
    viewLayout->setCurrentIndex(3);
    for (auto* projection : {xyProjection_, xzProjection_}) {
        connect(reset3DButton_, &QPushButton::clicked, projection, &EventProjectionWidget::fitView);
        connect(projection, &EventProjectionWidget::objectSelected, this, &MainWindow::selectInspectorObject);
        connect(grid, &QAction::toggled, projection, &EventProjectionWidget::setGridVisible);
        connect(crossings, &QAction::toggled, projection, &EventProjectionWidget::setCrossingsVisible);
        connect(geometry, &QAction::toggled, projection, &EventProjectionWidget::setGeometryVisible);
        connect(trajectories, &QAction::toggled, projection, &EventProjectionWidget::setTrajectoriesVisible);
    }
    connect(camera, &QComboBox::activated, detector3D_, [this](int index) {
        detector3D_->setCameraPreset(static_cast<DetectorViewport3D::CameraPreset>(index));
    });
    connect(grid, &QAction::toggled, detector3D_, &DetectorViewport3D::setGridVisible);
    connect(crossings, &QAction::toggled, detector3D_, &DetectorViewport3D::setCrossingsVisible);
    connect(frameTrackButton_, &QPushButton::clicked, detector3D_, &DetectorViewport3D::frameSelectedTrack);

    connect(previousEventButton_, &QPushButton::clicked,
            this, &MainWindow::previousInspectorEvent);
    connect(nextEventButton_, &QPushButton::clicked,
            this, &MainWindow::nextInspectorEvent);
    for (const auto& [key, button] : {
             std::pair{"Alt+Left", previousEventButton_}, std::pair{"Alt+Right", nextEventButton_}}) {
        auto* shortcut = new QShortcut(QKeySequence(key), page);
        shortcut->setContext(Qt::WidgetWithChildrenShortcut);
        connect(shortcut, &QShortcut::activated, button, &QPushButton::click);
    }
    connect(particleTable_, &QTableWidget::itemSelectionChanged, this, [this]() {
        const auto selected = particleTable_->selectionModel()->selectedRows();
        if (selected.isEmpty()) {
            selectInspectorObject(-1);
            return;
        }
        selectInspectorObject(particleTable_->item(selected.first().row(), 0)->text().toInt());
    });
    connect(detector3D_, &DetectorViewport3D::objectSelected,
            this, &MainWindow::selectInspectorObject);
    connect(detector3D_, &DetectorViewport3D::contextUnavailable,
            this, [this](const QString& reason) {
                statusLabel_->setText(reason);
                propertyInspector_->setPlainText(
                    "3D unavailable: " + reason
                    + "\n\nUse XY or XZ to inspect trajectories, or select a particle row.");
            });
    connect(reset3DButton_, &QPushButton::clicked,
            detector3D_, &DetectorViewport3D::resetCamera);
    connect(reset3DButton_, &QPushButton::clicked, camera, [camera] {
        camera->setCurrentIndex(0);
    });
    connect(trajectories, &QAction::toggled, this, [this](bool visible) {
        detector3D_->setTrajectoriesVisible(visible);
    });
    connect(geometry, &QAction::toggled, this, [this](bool visible) {
        detector3D_->setGeometryVisible(visible);
    });
}

void MainWindow::setInspectorEvent(const QJsonObject& event)
{
    currentEventData_ = heplab::EventDataAdapter::fromJson(event);
    frameTrackButton_->setEnabled(false);
    const auto trackCount = std::count_if(currentEventData_.tracks.cbegin(),
        currentEventData_.tracks.cend(), [](const auto& track) { return track.positionsM.size() > 1; });
    const bool collision = event.value("mode").toString() == "pythia";
    const auto info = event.value("event_info").toObject();
    if (!currentEventData_.valid) {
        eventSummaryLabel_->setText(QStringLiteral("Event unavailable"));
    } else if (collision && !info.isEmpty()) {
        const QString sel = info.value("selected").toBool(false)
            ? QStringLiteral("selected")
            : QStringLiteral("not selected");
        eventSummaryLabel_->setText(QString("%1 objects  ·  %2 trajectories  ·  w=%3  ·  %4")
            .arg(currentEventData_.tracks.size()).arg(trackCount)
            .arg(evidenceNumber(info, "weight"), sel));
    } else {
        eventSummaryLabel_->setText(QString("%1 objects  ·  %2 trajectories  ·  %3 model surfaces")
            .arg(currentEventData_.tracks.size()).arg(trackCount)
            .arg(currentEventData_.detectorSurfaces.size()));
    }
    trajectoryFilterAction_->setVisible(collision);
    if (!collision) {
        const QSignalBlocker blocker(trajectoryFilter_);
        trajectoryFilter_->setCurrentIndex(0);
    }
    refreshInspectorViews();
    {
        const QSignalBlocker blocker(particleTable_);
        particleTable_->clearSelection();
    }
    particleTable_->clearContents();
    geometryTable_->setRowCount(currentEventData_.detectorSurfaces.size());
    int surfaceRow = 0;
    for (const auto& surface : currentEventData_.detectorSurfaces) {
        const bool cylinder = surface.kind == DetectorSurface::Kind::Cylinder;
        geometryTable_->setItem(surfaceRow, 0, new QTableWidgetItem(surface.id));
        geometryTable_->setItem(surfaceRow, 1, new QTableWidgetItem(cylinder ? "Cylinder" : "Disk"));
        geometryTable_->setItem(surfaceRow, 2, new QTableWidgetItem(cylinder
            ? QString("r %1 · half length %2").arg(surface.radiusM).arg(surface.halfLengthM)
            : QString("z %1 · radii %2–%3").arg(surface.zM).arg(surface.innerRadiusM).arg(surface.outerRadiusM)));
        ++surfaceRow;
    }

    if (!currentEventData_.valid) {
        particleTable_->setRowCount(0);
        propertyInspector_->setPlainText(
            "Event rendering unavailable\n\n" + currentEventData_.diagnostic);
        return;
    }

    particleTable_->setColumnHidden(1, !collision);
    particleTable_->setColumnHidden(5, !collision);
    particleTable_->setRowCount(currentEventData_.tracks.size());
    for (int row = 0; row < currentEventData_.tracks.size(); ++row) {
        const heplab::DisplayTrack& track = currentEventData_.tracks.at(row);
        const int objectId = track.objectId;
        double pt = track.reconstructedPtGeV.value_or(0.0);
        if (track.momentum) {
            pt = std::hypot(track.momentum->pxGeV, track.momentum->pyGeV);
        }
        const QStringList values = {
            QString::number(objectId),
            track.collection.isEmpty() ? QStringLiteral("Truth") : track.collection,
            pdgSpeciesName(track.pdgId, track.collection),
            QString::number(track.chargeE, 'g', 5),
            track.momentum || track.reconstructedPtGeV
                ? QString::number(pt, 'g', 6) : QStringLiteral("n/a"),
            track.kind == heplab::DisplayObjectKind::GeneratedParticle
                ? QStringLiteral("PYTHIA8 truth")
                : track.kind == heplab::DisplayObjectKind::ReconstructedObject
                    ? QStringLiteral("DELPHES reco")
                    : QStringLiteral("Analytic object"),
            track.trajectoryModel + QStringLiteral(" · predicted crossings"),
        };
        for (int column = 0; column < values.size(); ++column) {
            auto* item = new QTableWidgetItem(values.at(column));
            item->setData(Qt::UserRole, track.stableIdentity);
            particleTable_->setItem(row, column, item);
        }
    }

    propertyInspector_->setHtml(formatEventOverviewHtml(event, currentEventData_, static_cast<int>(trackCount)));
}

void MainWindow::refreshInspectorViews()
{
    auto view = currentEventData_;
    const int filter = trajectoryFilter_->currentIndex();
    if (filter != 0) {
        for (auto& track : view.tracks) {
            const bool muon = std::abs(track.pdgId) == 13;
            if (muon == (filter == 1)) continue;
            track.positionsM.clear();
            track.predictedCrossings.clear();
        }
    }
    detector3D_->setEvent(view);
    xyProjection_->setEvent(view);
    xzProjection_->setEvent(view);
}

void MainWindow::clearInspectorEvent(const QString& message)
{
    currentEventData_ = {};
    trajectoryFilterAction_->setVisible(false);
    geometryTable_->setRowCount(0);
    completedEvent_ = {};
    detector3D_->clearEvent(message);
    xyProjection_->clearEvent(message);
    xzProjection_->clearEvent(message);
    particleTable_->clearContents();
    particleTable_->setRowCount(0);
    propertyInspector_->setPlainText(message);
    eventSummaryLabel_->setText(message);
    frameTrackButton_->setEnabled(false);
    eventIndexLabel_->setText("Event —");
    previousEventButton_->setEnabled(false);
    nextEventButton_->setEnabled(false);
}

void MainWindow::selectInspectorObject(int objectId)
{
    frameTrackButton_->setEnabled(false);
    detector3D_->setSelectedObjectId(objectId);
    xyProjection_->setSelectedObjectId(objectId);
    xzProjection_->setSelectedObjectId(objectId);

    if (objectId < 0) {
        const auto trackCount = std::count_if(currentEventData_.tracks.cbegin(),
            currentEventData_.tracks.cend(), [](const auto& track) { return track.positionsM.size() > 1; });
        propertyInspector_->setHtml(formatEventOverviewHtml(completedEvent_, currentEventData_, static_cast<int>(trackCount)));
        const QSignalBlocker blocker(particleTable_);
        particleTable_->clearSelection();
        return;
    }

    const heplab::DisplayTrack* selected = nullptr;
    for (const heplab::DisplayTrack& track : currentEventData_.tracks) {
        if (track.objectId == objectId) {
            selected = &track;
            break;
        }
    }
    if (!selected) {
        propertyInspector_->setPlainText(
            QString("Object %1 is not present in this event.").arg(objectId));
        return;
    }

    {
        const QSignalBlocker blocker(particleTable_);
        for (int row = 0; row < particleTable_->rowCount(); ++row) {
            if (particleTable_->item(row, 0)->text().toInt() == objectId) {
                particleTable_->selectRow(row);
                break;
            }
        }
    }

    const int filter = trajectoryFilter_->currentIndex();
    frameTrackButton_->setEnabled(selected->positionsM.size() > 1
        && (filter == 0 || (std::abs(selected->pdgId) == 13) == (filter == 1)));
    QStringList details;
    details << QString("Object ID: %1").arg(selected->objectId)
            << QString("Stable identity: %1").arg(selected->stableIdentity)
            << QString("Object kind: %1").arg(
                   heplab::displayObjectKindName(selected->kind))
            << QString("Species / PDG: %1").arg(pdgSpeciesName(selected->pdgId, selected->collection))
            << QString("Charge: %1 e").arg(selected->chargeE, 0, 'g', 8)
            << QString("Trajectory model: %1").arg(selected->trajectoryModel == "none" ? "No modeled trajectory" : selected->trajectoryModel)
            << QString("Trajectory samples: %1").arg(selected->positionsM.size())
            << QString("Predicted surface crossings: %1").arg(
                   selected->predictedCrossings.size());
    if (selected->initialPositionM) {
        const heplab::Position3M position = *selected->initialPositionM;
        details << QString("Source position [m]: (%1, %2, %3)")
            .arg(position.xM, 0, 'g', 8)
            .arg(position.yM, 0, 'g', 8)
            .arg(position.zM, 0, 'g', 8);
    }
    if (selected->momentum) {
        const heplab::MomentumGeV momentum = *selected->momentum;
        details << QString("Momentum [GeV/c]: (px=%1, py=%2, pz=%3)")
            .arg(momentum.pxGeV, 0, 'g', 8)
            .arg(momentum.pyGeV, 0, 'g', 8)
            .arg(momentum.pzGeV, 0, 'g', 8)
            << QString("Energy: %1 GeV").arg(momentum.energyGeV, 0, 'g', 8)
            << QString("Transverse momentum: %1 GeV/c")
                   .arg(std::hypot(momentum.pxGeV, momentum.pyGeV), 0, 'g', 8);
    } else if (selected->reconstructedPtGeV) {
        details << QString("Reconstructed pT: %1 GeV/c")
                       .arg(*selected->reconstructedPtGeV, 0, 'g', 8);
        if (selected->reconstructedEta) {
            details << QString("Reconstructed eta: %1")
                           .arg(*selected->reconstructedEta, 0, 'g', 8);
        }
        if (selected->reconstructedPhiRad) {
            details << QString("Reconstructed phi: %1 rad")
                           .arg(*selected->reconstructedPhiRad, 0, 'g', 8);
        }
    }
    if (!selected->predictedCrossings.isEmpty()) {
        details << QString() << "Predicted crossings by surface";
        for (const auto& crossing : selected->predictedCrossings) {
            details << QString("%1  (%2, %3, %4) m").arg(crossing.surfaceId)
                .arg(crossing.positionM.xM, 0, 'g', 4)
                .arg(crossing.positionM.yM, 0, 'g', 4)
                .arg(crossing.positionM.zM, 0, 'g', 4);
        }
    }
    details << QString() << "Display coordinates use metres; momenta use GeV/c."
            << "Trajectory samples and detector crossings are model predictions, not measured hits.";
    QString formatted = "<h3 style='margin:0 0 10px'>Track details</h3>";
    for (const QString& detail : details) {
        if (detail.isEmpty()) continue;
        const qsizetype separator = detail.indexOf(QStringLiteral(": "));
        if (separator >= 0) {
            formatted += "<p style='margin:0 0 7px'><b>"
                + detail.left(separator + 1).toHtmlEscaped() + "</b><br>"
                + detail.mid(separator + 2).toHtmlEscaped() + "</p>";
        } else if (detail == "Predicted crossings by surface") {
            formatted += "<h4 style='margin:12px 0 5px'>" + detail.toHtmlEscaped() + "</h4>";
        } else {
            formatted += "<p style='margin:0 0 5px'>" + detail.toHtmlEscaped() + "</p>";
        }
    }
    propertyInspector_->setHtml(formatted);
}

QString MainWindow::findRepositoryRoot() const
{
    if (!qEnvironmentVariable("HEPLAB_REPOSITORY_ROOT").isEmpty()) {
        return QDir::cleanPath(qEnvironmentVariable("HEPLAB_REPOSITORY_ROOT"));
    }
    QDir directory(QCoreApplication::applicationDirPath());
    for (int depth = 0; depth < 8; ++depth) {
        if (QFileInfo::exists(directory.filePath("CMakeLists.txt"))
            && QFileInfo::exists(directory.filePath("pyproject.toml"))) {
            return QDir::cleanPath(directory.absolutePath());
        }
        if (!directory.cdUp()) {
            break;
        }
    }
    return {};
}

void MainWindow::buildHomePage(QWidget* page)
{
    auto* layout = qobject_cast<QVBoxLayout*>(page->layout());
    auto* controls = new QWidget(page);
    auto* controlLayout = new QHBoxLayout(controls);
    projectName_ = new QLineEdit(controls);
    projectName_->setPlaceholderText("Project name");
    auto* newButton = new QPushButton("New Project", controls);
    auto* openButton = new QPushButton("Open", controls);
    auto* renameButton = new QPushButton("Rename", controls);
    auto* saveButton = new QPushButton("Save Configuration", controls);
    controlLayout->addWidget(projectName_);
    controlLayout->addWidget(newButton);
    controlLayout->addWidget(openButton);
    controlLayout->addWidget(renameButton);
    controlLayout->addWidget(saveButton);
    controlLayout->addStretch();

    projectList_ = new QListWidget(page);
    runList_ = new QTableWidget(0, 3, page);
    runList_->setObjectName("projectRuns");
    runList_->setHorizontalHeaderLabels({"Run ID", "Status", "Backend"});
    runList_->horizontalHeader()->setSectionResizeMode(0, QHeaderView::Stretch);
    runList_->horizontalHeader()->setSectionResizeMode(1, QHeaderView::ResizeToContents);
    runList_->horizontalHeader()->setSectionResizeMode(2, QHeaderView::ResizeToContents);
    runList_->verticalHeader()->hide();
    runList_->verticalHeader()->setDefaultSectionSize(30);
    runList_->setShowGrid(false);
    runList_->setAlternatingRowColors(true);
    runList_->setSelectionBehavior(QAbstractItemView::SelectRows);
    runList_->setEditTriggers(QAbstractItemView::NoEditTriggers);
    historyFilter_ = new QLineEdit(page);
    historyFilter_->setPlaceholderText("Filter by run ID, status or backend");
    historyFilter_->setClearButtonEnabled(true);
    connect(historyFilter_, &QLineEdit::textChanged, this, &MainWindow::filterRunHistory);
    projectList_->setSelectionMode(QAbstractItemView::SingleSelection);
    runList_->setSelectionMode(QAbstractItemView::SingleSelection);
    auto* inspectRun = new QPushButton("Inspect completed run", page);
    connect(inspectRun, &QPushButton::clicked, this, [this] {
        const auto* item = runList_->item(runList_->currentRow(), 0);
        const auto run = item ? item->data(Qt::UserRole).toJsonObject() : QJsonObject{};
        if (run.value("status").toString() != "completed" || !worker_ ||
            !worker_->isRunning() || !runButton_->isEnabled()) {
            statusLabel_->setText("Select a completed run when the worker is idle.");
            return;
        }
        currentRunId_ = run.value("id").toString();
        runButton_->setEnabled(false);
        QJsonObject arguments{{"job_id", currentRunId_}};
        pollRequestId_ = worker_->sendRequest("jobs.get", arguments);
    });
    connect(runList_, &QTableWidget::itemDoubleClicked, inspectRun, &QPushButton::click);


    auto* lists = new QHBoxLayout();
    auto* projectColumn = new QVBoxLayout();
    projectColumn->addWidget(new QLabel("Projects", page));
    projectColumn->addWidget(projectList_);
    auto* runColumn = new QVBoxLayout();
    runColumn->addWidget(new QLabel("Run History", page));
    auto* historyTools = new QHBoxLayout;
    historyTools->addWidget(historyFilter_, 1);
    auto* sortRuns = new QCheckBox("Sort by ID", page);
    connect(sortRuns, &QCheckBox::toggled, this, [this](bool enabled) {
        sortHistoryById_ = enabled;
        renderRunHistory();
    });
    historyTools->addWidget(sortRuns);
    runColumn->addLayout(historyTools);
    runColumn->addWidget(runList_);
    auto* metadata = new QLabel("Select a run to see its parameters.", page);
    metadata->setWordWrap(true);
    metadata->setTextFormat(Qt::PlainText);
    metadata->setTextInteractionFlags(Qt::TextSelectableByMouse);
    connect(runList_, &QTableWidget::currentCellChanged, metadata, [this, metadata](int row) {
        const auto* item = runList_->item(row, 0);
        if (!item) {
            metadata->setText("Select a run to see its parameters.");
            return;
        }
        const auto run = item->data(Qt::UserRole).toJsonObject();
        const auto config = run.value("config").toObject();
        metadata->setText(QString("%1  ·  %2\nBackend %3  ·  Seed %4  ·  Event budget %5")
            .arg(run.value("id").toString(), run.value("status").toString(),
                 config.value("backend").toString("Unavailable"),
                 evidenceNumber(config, "seed"), evidenceNumber(config, "events")));
    });
    runColumn->addWidget(metadata);
    runColumn->addWidget(inspectRun);
    lists->addLayout(projectColumn, 1);
    lists->addLayout(runColumn, 2);

    layout->addWidget(controls);
    layout->addLayout(lists);

    connect(newButton, &QPushButton::clicked, this, &MainWindow::createProject);
    connect(openButton, &QPushButton::clicked, this, &MainWindow::openSelectedProject);
    connect(renameButton, &QPushButton::clicked, this, &MainWindow::renameSelectedProject);
    connect(saveButton, &QPushButton::clicked, this, &MainWindow::saveActiveProject);
    refreshProjectList();
}

void MainWindow::renderRunHistory()
{
    const auto* selected = runList_->item(runList_->currentRow(), 0);
    const QString selectedId = selected ? selected->text() : QString();
    QVector<QJsonObject> runs;
    runs.reserve(runHistory_.size());
    for (const auto& entry : runHistory_) runs.append(entry.toObject());
    if (sortHistoryById_) {
        std::sort(runs.begin(), runs.end(), [](const auto& first, const auto& second) {
            return first.value("id").toString() < second.value("id").toString();
        });
    }
    runList_->setRowCount(0);
    runList_->setRowCount(runs.size());
    QFont idFont = QFontDatabase::systemFont(QFontDatabase::FixedFont);
    idFont.setPointSizeF(runList_->font().pointSizeF());
    for (int row = 0; row < runs.size(); ++row) {
        const auto& run = runs.at(row);
        auto* id = new QTableWidgetItem(run.value("id").toString());
        id->setFont(idFont);
        id->setData(Qt::UserRole, run);
        id->setToolTip(id->text());
        runList_->setItem(row, 0, id);
        const auto status = run.value("status").toString();
        QString displayStatus = status;
        if (!displayStatus.isEmpty()) displayStatus[0] = displayStatus[0].toUpper();
        runList_->setItem(row, 1, new QTableWidgetItem(displayStatus));
        runList_->setItem(row, 2, new QTableWidgetItem(
            run.value("config").toObject().value("backend").toString("Unavailable")));
        if (id->text() == selectedId) runList_->setCurrentCell(row, 0);
    }
    filterRunHistory();
}

void MainWindow::filterRunHistory()
{
    const QString query = historyFilter_->text().trimmed();
    for (int row = 0; row < runList_->rowCount(); ++row) {
        QStringList fields;
        for (int column = 0; column < runList_->columnCount(); ++column)
            fields << runList_->item(row, column)->text();
        runList_->setRowHidden(row, !fields.join(' ').contains(query, Qt::CaseInsensitive));
    }
    const int current = runList_->currentRow();
    if (current >= 0 && runList_->isRowHidden(current)) {
        runList_->clearSelection();
        runList_->setCurrentCell(-1, -1);
    }
}

void MainWindow::refreshProjectList()
{
    if (!projectList_) {
        return;
    }
    if (activeProjectLabel_)
        activeProjectLabel_->setText(projects_->project(projects_->activeProjectId()).value("name").toString());
    projectList_->clear();
    for (const QString& id : projects_->projectIds()) {
        const QJsonObject entry = projects_->project(id);
        auto* item = new QListWidgetItem(entry.value("name").toString());
        item->setData(Qt::UserRole, id);
        projectList_->addItem(item);
        if (id == projects_->activeProjectId()) {
            projectList_->setCurrentItem(item);
        }
    }
}

void MainWindow::createProject()
{
    if (stopButton_->isEnabled() || pollTimer_->isActive()) {
        statusLabel_->setText("Finish or cancel the active run before switching projects.");
        return;
    }
    const QString name = projectName_->text().trimmed();
    const QString id = projects_->createProject(name.isEmpty() ? "Untitled Project" : name);
    if (id.isEmpty()) {
        statusLabel_->setText("Could not create project");
        return;
    }
    projectRoot_ = projects_->activeProjectRoot();
    if (learning_) learning_->recordProjectOpened();
    refreshProjectList();
    currentRunId_.clear();
    completedJob_ = {};
    clearInspectorEvent("Select a completed run or start a simulation in this project.");
    eventIndexLabel_->setText("Event: none");
    resultView_->clear();
    resultSummary_->setPlainText("Select a completed run or start an experiment.");
    scientificPlot_->setResult({});
    refreshComparisonAxes();
    refreshCutflow();
    compareButton_->setEnabled(false);
    saveButton_->setEnabled(false);
    if (worker_) {
        runButton_->setEnabled(false);
        worker_->restart(findRepositoryRoot(), projectRoot_);
    }
    statusLabel_->setText("Created project " + projects_->project(id).value("name").toString());
}

void MainWindow::openSelectedProject()
{
    if (stopButton_->isEnabled() || pollTimer_->isActive()) {
        statusLabel_->setText("Finish or cancel the active run before switching projects.");
        return;
    }
    if (!projectList_->currentItem()) {
        return;
    }
    const QString id = projectList_->currentItem()->data(Qt::UserRole).toString();
    if (!projects_->openProject(id)) {
        statusLabel_->setText("Could not open project");
        return;
    }
    projectRoot_ = projects_->activeProjectRoot();
    if (learning_) learning_->recordProjectOpened();
    refreshProjectList();
    currentRunId_.clear();
    completedJob_ = {};
    clearInspectorEvent("Select a completed run or start a simulation in this project.");
    eventIndexLabel_->setText("Event: none");
    resultView_->clear();
    resultSummary_->setPlainText("Select a completed run or start an experiment.");
    scientificPlot_->setResult({});
    refreshComparisonAxes();
    refreshCutflow();
    compareButton_->setEnabled(false);
    saveButton_->setEnabled(false);
    if (worker_) {
        runButton_->setEnabled(false);
        worker_->restart(findRepositoryRoot(), projectRoot_);
    }
    QFile manifest(projectRoot_ + "/project.json");
    if (manifest.open(QIODevice::ReadOnly)) {
        QJsonParseError error;
        const QJsonDocument document =
            QJsonDocument::fromJson(manifest.readAll(), &error);
        if (error.error == QJsonParseError::NoError && document.isObject()) {
            const QJsonObject config =
                document.object().value("configuration").toObject();
            if (!config.isEmpty()) {
                experiment_->setCurrentIndex(config.value("mode").toString() == "pythia" ? 1 : 0);
                muonPtCut_->setValue(config.value("muon_pt_min_gev").toDouble(20));
                muonEtaCut_->setValue(config.value("muon_abs_eta_max").toDouble(2.4));
                muonIsoCut_->setValue(config.value("muon_iso_max").toDouble(0.15));
                seed_->setValue(config.value("seed").toInt(seed_->value()));
                particleSource_->setCurrentIndex(
                    config.value("source_model").toString() == "angular_sample" ? 1 : 0);
                eventBudget_->setValue(
                    config.value("events").toInt(eventBudget_->value()));
                momentum_->setValue(
                    config.value("momentum_gev").toDouble(momentum_->value()));
                field_->setValue(
                    config.value("bz_tesla").toDouble(field_->value()));
                thickness_->setValue(
                    config.value("thickness_mm").toDouble(thickness_->value()));
            }
        }
    }
    statusLabel_->setText("Opened project " + projects_->project(id).value("name").toString());
}

void MainWindow::renameSelectedProject()
{
    if (!projectList_->currentItem()) {
        return;
    }
    const QString id = projectList_->currentItem()->data(Qt::UserRole).toString();
    const QString name = projectName_->text().trimmed();
    if (!projects_->renameProject(id, name.isEmpty() ? "Untitled Project" : name)) {
        statusLabel_->setText("Could not rename project");
        return;
    }
    refreshProjectList();
    statusLabel_->setText("Renamed project");
}

void MainWindow::saveActiveProject()
{
    const QString id = projects_->activeProjectId();
    if (id.isEmpty()) {
        statusLabel_->setText("No active project");
        return;
    }
    const auto config = simulationConfig();
    if (!projects_->saveProject(id, config, currentRunId_)) {
        statusLabel_->setText("Could not save project");
        return;
    }
    statusLabel_->setText("Saved project configuration");
}

void MainWindow::buildSimulationPage(QWidget* page)
{
    auto* layout = qobject_cast<QVBoxLayout*>(page->layout());
    auto* formWidget = new QWidget(page);
    auto* form = new QFormLayout(formWidget);

    experiment_ = new QComboBox(formWidget);
    experiment_->setObjectName("simulationExperiment");
    experiment_->addItems({"Analytic muon thin-slab bench", "pp collision · PYTHIA8 / DELPHES"});
    particleSource_ = new QComboBox(formWidget);
    particleSource_->setObjectName("particleSource");
    particleSource_->addItem("Transverse pair", "transverse_pair");
    particleSource_->addItem("Angular sample", "angular_sample");
    particleSource_->setToolTip("The transverse bench produces one event. Angular sampling supports 1–200 events.");
    seed_ = new QSpinBox(formWidget);
    seed_->setRange(1, 900000000);
    seed_->setValue(42);
    eventBudget_ = new QSpinBox(formWidget);
    eventBudget_->setObjectName("eventBudget");
    eventBudget_->setRange(1, 1);
    eventBudget_->setValue(1);
    momentum_ = new QDoubleSpinBox(formWidget);
    momentum_->setObjectName("muonMomentum");
    momentum_->setRange(1.0, 100.0);
    momentum_->setDecimals(3);
    momentum_->setSuffix(" GeV/c");
    momentum_->setValue(2.0);
    field_ = new QDoubleSpinBox(formWidget);
    field_->setRange(-8.0, 8.0);
    field_->setDecimals(3);
    field_->setSuffix(" T");
    field_->setValue(3.8);
    thickness_ = new QDoubleSpinBox(formWidget);
    thickness_->setRange(0.1, 5.0);
    thickness_->setDecimals(3);
    thickness_->setSuffix(" mm");
    thickness_->setValue(1.0);

    auto* setup = new QGroupBox("Experiment setup", formWidget);
    auto* setupFields = new QFormLayout(setup);
    setupFields->addRow("Experiment", experiment_);
    auto* presets = new QComboBox(setup);
    presets->setObjectName("simulationPresets");
    presets->addItem("Custom / Choose a preset…");
    presets->addItem("Visible magnetic bending · 2 GeV/c", 2.0);
    presets->addItem("Zero-field control · 2 GeV/c", 2.0);
    presets->addItem("Intermediate momentum · 10 GeV/c", 10.0);
    presets->addItem("High-momentum reference · 45 GeV/c", 45.0);
    connect(presets, &QComboBox::activated, this, [this, presets](int index) {
        if (index == 0) return;
        const QSignalBlocker b1(field_), b2(momentum_), b3(thickness_);
        field_->setValue(index == 2 ? 0.0 : 3.8);
        momentum_->setValue(presets->itemData(index).toDouble());
        thickness_->setValue(1.0);
        emit momentum_->valueChanged(momentum_->value());
    });
    const auto syncCustomPreset = [presets] {
        const QSignalBlocker blocker(presets);
        presets->setCurrentIndex(0);
    };
    connect(momentum_, &QDoubleSpinBox::valueChanged, presets, syncCustomPreset);
    connect(field_, &QDoubleSpinBox::valueChanged, presets, syncCustomPreset);
    connect(thickness_, &QDoubleSpinBox::valueChanged, presets, syncCustomPreset);
    setupFields->addRow("Presets", presets);
    setupFields->addRow("Random seed", seed_);
    setupFields->addRow("Particle source", particleSource_);
    setupFields->addRow("Event budget", eventBudget_);
    eventBudget_->setEnabled(false);
    const auto updateBudget = [this] {
        const bool collision = experiment_->currentIndex() == 1;
        const bool angular = particleSource_->currentIndex() == 1;
        eventBudget_->setMaximum(collision ? 1000 : angular ? 200 : 1);
        eventBudget_->setEnabled(collision || angular);
    };
    connect(particleSource_, &QComboBox::currentIndexChanged, eventBudget_, updateBudget);
    auto* physical = new QGroupBox("Initial conditions and material", formWidget);
    auto* physicalFields = new QFormLayout(physical);
    physicalFields->addRow("Muon momentum", momentum_);
    physicalFields->addRow("Axial magnetic field", field_);
    physicalFields->addRow("Silicon thickness", thickness_);
    auto* columns = new QHBoxLayout;
    columns->addWidget(setup, 1);
    columns->addWidget(physical, 1);
    auto* cuts = new QGroupBox("Reconstructed dimuon selection", formWidget);
    auto* cutFields = new QFormLayout(cuts);
    const auto addCut = [cuts, cutFields](const QString& label, double minimum, double maximum, double initial) {
        auto* control = new QDoubleSpinBox(cuts);
        control->setDecimals(2);
        control->setRange(minimum, maximum);
        control->setValue(initial);
        cutFields->addRow(label, control);
        return control;
    };
    muonPtCut_ = addCut("Minimum pT [GeV/c]", 0, 500, 20);
    muonEtaCut_ = addCut("Maximum |η|", 0.01, 2.4, 2.4);
    muonIsoCut_ = addCut("Maximum relative isolation", 0, 10, 0.15);
    columns->addWidget(cuts, 1);
    cuts->hide();
    connect(experiment_, &QComboBox::currentIndexChanged, formWidget,
        [this, physical, cuts, presets, updateBudget](int index) {
            const bool collision = index == 1;
            physical->setVisible(!collision);
            cuts->setVisible(collision);
            presets->setEnabled(!collision);
            particleSource_->setEnabled(!collision);
            updateBudget();
            if (collision) eventBudget_->setValue(20);
        });
    form->addRow(columns);
    field_->setToolTip("Signed axial field in the ideal solenoid bore. Outside the bore propagation is straight.");
    thickness_->setToolTip("Thickness of the single silicon slab at one metre of path length.");
    auto* preflight = new QLabel(formWidget);
    preflight->setWordWrap(true);
    const auto updatePreflight = [this, preflight] {
        if (experiment_->currentIndex() == 1) {
            preflight->setText(QString("13 TeV Drell–Yan pp · PYTHIA8 generator and DELPHES CMS fast simulation\n"
                                       "%1 events · seed %2 · requires the pinned Linux/WSL runtime")
                .arg(eventBudget_->value()).arg(seed_->value()));
            return;
        }
        preflight->setText(QString("Analytic teaching model · %1 · 1 silicon slab\n"
                                  "%2 GeV/c per muon · %3 T axial field · seed %4 · %5 event(s)")
                           .arg(particleSource_->currentText())
                           .arg(momentum_->value(), 0, 'g', 4).arg(field_->value(), 0, 'g', 4)
                           .arg(seed_->value()).arg(eventBudget_->value()));
    };
    connect(experiment_, &QComboBox::currentIndexChanged, preflight, updatePreflight);
    connect(momentum_, &QDoubleSpinBox::valueChanged, preflight, updatePreflight);
    connect(field_, &QDoubleSpinBox::valueChanged, preflight, updatePreflight);
    connect(seed_, &QSpinBox::valueChanged, preflight, updatePreflight);
    connect(eventBudget_, &QSpinBox::valueChanged, preflight, updatePreflight);
    connect(particleSource_, &QComboBox::currentIndexChanged, preflight, updatePreflight);
    updatePreflight();
    form->addRow("Preflight", preflight);

    runButton_ = new QPushButton("Run", formWidget);
    runButton_->setObjectName("runExperiment");
    runButton_->setProperty("primary", true);
    runButton_->setEnabled(false);
    stopButton_ = new QPushButton("Stop", formWidget);
    stopButton_->setEnabled(false);
    saveButton_ = new QPushButton("Save result", formWidget);
    saveButton_->setEnabled(false);
    auto* actions = new QHBoxLayout();
    actions->addWidget(runButton_);
    actions->addWidget(stopButton_);
    actions->addWidget(saveButton_);
    auto* reset = new QPushButton("Reset defaults", formWidget);
    actions->addWidget(reset);
    connect(reset, &QPushButton::clicked, this, [this] {
        experiment_->setCurrentIndex(0);
        muonPtCut_->setValue(20);
        muonEtaCut_->setValue(2.4);
        muonIsoCut_->setValue(0.15);
        seed_->setValue(42);
        particleSource_->setCurrentIndex(0);
        eventBudget_->setValue(1);
        momentum_->setValue(2.0);
        field_->setValue(3.8);
        thickness_->setValue(1.0);
    });
    actions->addStretch();
    form->addRow(actions);

    resultView_ = new QTextEdit(page);
    resultView_->setReadOnly(true);
    resultView_->setPlaceholderText("No committed result.");

    layout->addWidget(formWidget);
    resultSummary_ = new QTextBrowser(page);
    resultSummary_->setObjectName("experimentResult");
    resultSummary_->setPlainText("Run the experiment to inspect its committed result.");
    layout->addWidget(resultSummary_, 2);
    addTechnicalDetails(layout, resultView_);

    connect(runButton_, &QPushButton::clicked, this, &MainWindow::startSimulationRun);
    connect(stopButton_, &QPushButton::clicked, this, &MainWindow::cancelCurrentRun);
    connect(saveButton_, &QPushButton::clicked, this, &MainWindow::saveCommittedResult);
}

void MainWindow::handleWorkerHandshake(const QJsonObject& handshake)
{
    statusLabel_->setText(QString("Worker ready: %1 / %2")
                              .arg(handshake.value("protocol").toString(),
                                   handshake.value("worker_version").toString()));
    runButton_->setEnabled(true);
    refreshRunHistory();
    evidenceRequestId_ = worker_->sendRequest("project.evidence");
    datasetListRequestId_ =
        worker_->sendRequest("datasets.list");
}

void MainWindow::refreshRunHistory()
{
    if (!worker_ || !worker_->isRunning()) {
        return;
    }
    runHistoryRequestId_ = worker_->sendRequest("jobs.list");
}

QJsonObject MainWindow::simulationConfig() const
{
    QJsonObject config;
    const bool collision = experiment_->currentIndex() == 1;
    config["mode"] = collision ? "pythia" : "analytic";
    config["backend"] = collision ? "delphes" : "reference";
    config["seed"] = seed_->value();
    config["events"] = eventBudget_->value();
    config["momentum_gev"] = momentum_->value();
    config["bz_tesla"] = field_->value();
    config["thickness_mm"] = thickness_->value();
    config["response_model"] = "ideal";
    config["field_model"] = "ideal_bore";
    config["source_model"] = particleSource_->currentData().toString();
    if (collision) {
        config["muon_pt_min_gev"] = muonPtCut_->value();
        config["muon_abs_eta_max"] = muonEtaCut_->value();
        config["muon_iso_max"] = muonIsoCut_->value();
    }
    return config;
}

int MainWindow::completedEventCount() const
{
    const auto result = completedJob_.value("result").toObject();
    return result.value("events").toInt(result.value("summary").toObject()
        .value("events").toInt(completedJob_.value("config").toObject().value("events").toInt(1)));
}

void MainWindow::startSimulationRun()
{
    if (!runButton_->isEnabled() || !worker_ || !worker_->isRunning()) {
        statusLabel_->setText("Worker unavailable");
        return;
    }
    completedJob_ = {};
    completedEvent_ = {};
    clearInspectorEvent("Run in progress. The completed event will appear here automatically.");
    saveButton_->setEnabled(false);
    compareButton_->setEnabled(false);
    scientificPlot_->setResult({});
    refreshComparisonAxes();
    refreshCutflow();

    const auto config = simulationConfig();

    QJsonObject args;
    args["config"] = config;
    args["idempotency_key"] =
        "qt-" + QUuid::createUuid().toString(QUuid::WithoutBraces).left(32);
    submitRequestId_ = worker_->sendRequest("jobs.submit", args);
    runButton_->setEnabled(false);
    stopButton_->setEnabled(true);
    resultSummary_->setPlainText("Submitting the experiment…");
    statusLabel_->setText("Submitting run");
}

void MainWindow::pollCurrentRun()
{
    if (currentRunId_.isEmpty() || !worker_) {
        return;
    }
    QJsonObject args;
    args["job_id"] = currentRunId_;
    pollRequestId_ = worker_->sendRequest("jobs.get", args);
}

void MainWindow::cancelCurrentRun()
{
    if (currentRunId_.isEmpty()) {
        return;
    }
    QJsonObject args;
    args["job_id"] = currentRunId_;
    worker_->sendRequest("jobs.cancel", args);
}

void MainWindow::previousInspectorEvent()
{
    if (inspectorEventIndex_ <= 0 || currentRunId_.isEmpty()) {
        return;
    }
    inspectorEventIndex_ -= 1;
    clearInspectorEvent(QString("Loading event %1 from the completed run…")
                            .arg(inspectorEventIndex_));
    QJsonObject args;
    args["job_id"] = currentRunId_;
    args["index"] = inspectorEventIndex_;
    eventRequestId_ = worker_->sendRequest("jobs.event", args);
}

void MainWindow::nextInspectorEvent()
{
    if (currentRunId_.isEmpty()) {
        return;
    }
    const int eventCount = completedEventCount();
    if (inspectorEventIndex_ + 1 >= eventCount) {
        return;
    }
    inspectorEventIndex_ += 1;
    clearInspectorEvent(QString("Loading event %1 from the completed run…")
                            .arg(inspectorEventIndex_));
    QJsonObject args;
    args["job_id"] = currentRunId_;
    args["index"] = inspectorEventIndex_;
    eventRequestId_ = worker_->sendRequest("jobs.event", args);
}

void MainWindow::handleWorkerResponse(int requestId, const QJsonObject& response)
{
    if (requestId == evidenceRequestId_) {
        if (response.value("ok").toBool())
            validationSummary_->setHtml(validationReport(response.value("result").toObject()));
        else
            validationSummary_->setPlainText(response.value("error").toObject().value("message").toString("Validation evidence unavailable."));
        validationView_->setPlainText(response.value("ok").toBool()
            ? QString::fromUtf8(QJsonDocument::fromVariant(response.value("result").toVariant()).toJson(QJsonDocument::Indented))
            : response.value("error").toObject().value("message").toString("Validation evidence unavailable."));
        return;
    }
    if (requestId == datasetListRequestId_) {
        if (response.value("ok").toBool())
            openData_->setManifests(response.value("result").toArray());
        else
            openData_->setCatalogError(response.value("error").toObject().value("message").toString());
        return;
    }

    if (requestId == runHistoryRequestId_) {
        if (runList_ && response.value("ok").toBool()) {
            runHistory_ = response.value("result").toArray();
            renderRunHistory();
        }
        return;
    }

    if (requestId == submitRequestId_) {
        if (!response.value("ok").toBool()) {
            statusLabel_->setText(response["error"].toObject().value("message").toString());
            resultSummary_->setPlainText(statusLabel_->text());
            clearInspectorEvent("Run submission failed. Review the worker diagnostic in the status bar.");
            runButton_->setEnabled(true);
            stopButton_->setEnabled(false);
            return;
        }
        currentRunId_ = response["result"].toObject().value("id").toString();
        statusLabel_->setText("Running " + currentRunId_);
        pollTimer_->start();
        return;
    }

    if (requestId == pollRequestId_) {
        if (!response.value("ok").toBool()) {
            pollTimer_->stop();
            statusLabel_->setText(response["error"].toObject().value("message").toString());
            resultSummary_->setPlainText(statusLabel_->text());
            runButton_->setEnabled(true);
            stopButton_->setEnabled(false);
            return;
        }
        const QJsonObject result = response["result"].toObject();
        const QString status = result.value("status").toString();
        const auto progress = result.value("progress").toObject();
        const bool active = status == "running" || status == "queued";
        progress_->setRange(0, progress.value("total").toInt());
        progress_->setValue(progress.value("completed").toInt());
        progress_->setVisible(active);

        statusLabel_->setText(status == "running" ? "Running " + currentRunId_
                                                   : status + " " + currentRunId_);
        if (status == "completed") {
            pollTimer_->stop();
            completedJob_ = result;
            if (scientificPlot_) {
                QJsonObject plotResult =
                    result.value("result").toObject();
                if (plotResult.isEmpty()) {
                    plotResult = result;
                }
                scientificPlot_->setResult(plotResult);
                refreshComparisonAxes();
                refreshCutflow();
                compareButton_->setEnabled(!plotResult.value("analysis").toObject().isEmpty());
            }
            inspectorEventIndex_ = 0;
            QJsonObject args;
            args["job_id"] = currentRunId_;
            args["index"] = 0;
            eventRequestId_ = worker_->sendRequest("jobs.event", args);
        } else if (status == "cancelled" || status == "failed") {
            pollTimer_->stop();
            runButton_->setEnabled(true);
            stopButton_->setEnabled(false);
            saveButton_->setEnabled(false);
            clearInspectorEvent(result.value("error").toString(
                status == "cancelled" ? "Run cancelled." : "Run failed."));
            resultSummary_->setPlainText(result.value("error").toString(
                status == "cancelled" ? "Run cancelled." : "Run failed."));
            currentRunId_.clear();
        }
        return;
    }

    if (requestId == eventRequestId_) {
        if (!response.value("ok").toBool()) {
            const QString error = response["error"].toObject().value("message").toString();
            clearInspectorEvent("Could not load event: " + error);
            statusLabel_->setText(error);
            runButton_->setEnabled(true);
            stopButton_->setEnabled(false);
            return;
        }
        completedEvent_ = response["result"].toObject();
        setInspectorEvent(completedEvent_);
        if (currentEventData_.valid) learning_->recordEventViewed(completedEvent_);
        selectInspectorObject(-1);
        const int eventCount = completedEventCount();
        eventIndexLabel_->setText(QString("Event %1 of %2")
            .arg(inspectorEventIndex_ + 1).arg(std::max(eventCount, inspectorEventIndex_ + 1)));
        previousEventButton_->setEnabled(inspectorEventIndex_ > 0);
        nextEventButton_->setEnabled(
            inspectorEventIndex_ + 1 < eventCount);
        resultView_->setPlainText(QJsonDocument(completedEvent_).toJson(QJsonDocument::Indented));
        const auto artifact = completedJob_.value("result").toObject();
        const auto config = completedJob_.value("config").toObject();
        const auto provenance = artifact.value("artifact").toObject();
        resultSummary_->setHtml(QString(
            "<h2>Committed experiment</h2>"
            "<table cellspacing='8'>"
            "<tr><td>Run ID</td><td>%1</td></tr>"
            "<tr><td>Backend</td><td>%2</td></tr>"
            "<tr><td>Events</td><td>%3</td></tr>"
            "<tr><td>Selected event</td><td>%4</td></tr>"
            "<tr><td>Displayed objects</td><td>%5</td></tr>"
            "<tr><td>Trajectory segments</td><td>%6</td></tr>"
            "<tr><td>Artifact fingerprint</td><td>%7</td></tr></table>"
            "<p>Trajectories and surface crossings are model predictions.</p>")
            .arg(currentRunId_.toHtmlEscaped(), config.value("backend").toString().toHtmlEscaped())
            .arg(eventCount).arg(inspectorEventIndex_).arg(currentEventData_.tracks.size())
            .arg(currentEventData_.trajectorySegmentCount())
            .arg(provenance.value("result_sha256").toString("Unavailable").toHtmlEscaped()));
        if (navigation_) navigation_->setCurrentRow(2);
        statusLabel_->setText(currentEventData_.valid
            ? QString("Loaded event %1 · %2 objects")
                  .arg(inspectorEventIndex_).arg(currentEventData_.tracks.size())
            : "Event loaded with a rendering diagnostic");
        projects_->saveProject(projects_->activeProjectId(), {}, currentRunId_);
        refreshRunHistory();
        runButton_->setEnabled(true);
        stopButton_->setEnabled(false);
        saveButton_->setEnabled(true);
    }
}

void MainWindow::saveCommittedResult()
{
    if (completedJob_.isEmpty() || completedEvent_.isEmpty()) {
        return;
    }
    const QString path = QFileDialog::getSaveFileName(
        this, "Save reproducible HEPLab result",
        "heplab-result.json", "HEPLab JSON (*.json)");
    if (path.isEmpty()) {
        return;
    }
    QJsonObject envelope;
    envelope["schema"] = "heplab-native-result-v1";
    envelope["run_id"] = currentRunId_;
    envelope["project_root"] = projectRoot_;
    envelope["worker"] = "heplab-desktop-ipc-v1";
    envelope["job"] = completedJob_;
    envelope["event"] = completedEvent_;
    envelope["created_utc"] =
        QDateTime::currentDateTimeUtc().toString(Qt::ISODate);
    const QByteArray envelopePayload =
        QJsonDocument(envelope).toJson(QJsonDocument::Compact);
    envelope["payload_sha256"] =
        QString::fromLatin1(
            QCryptographicHash::hash(
                envelopePayload, QCryptographicHash::Sha256).toHex());

    QSaveFile file(path);
    if (!file.open(QIODevice::WriteOnly)) {
        statusLabel_->setText("Could not save result: " + file.errorString());
        return;
    }
    const auto payload = QJsonDocument(envelope).toJson(QJsonDocument::Indented);
    if (file.write(payload) != payload.size() || !file.commit()) {
        statusLabel_->setText("Could not publish result: " + file.errorString());
        return;
    }
    statusLabel_->setText("Saved " + path);
}

} // namespace heplab
