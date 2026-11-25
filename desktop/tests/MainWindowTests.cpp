#include "MainWindow.h"
#include "WorkerClient.h"
#include "ProjectStore.h"
#include "EventProjectionWidget.h"
#include "DetectorViewport3D.h"
#include "ScientificPlotWidget.h"

#include <QApplication>
#include <QAction>
#include <QComboBox>
#include <QSettings>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QImage>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QMainWindow>
#include <QListWidget>
#include <QTableWidget>
#include <QTextEdit>
#include <QTextBrowser>
#include <QCheckBox>
#include <QPushButton>
#include <QScopeGuard>
#include <QSpinBox>
#include <QTabWidget>
#include <QSignalSpy>
#include <QStackedWidget>
#include <QStatusBar>
#include <QTemporaryDir>
#include <QWheelEvent>
#include <QtTest>

namespace {

QJsonObject analyticFixture()
{
    QFile fixture(QDir(QT_TESTCASE_SOURCEDIR)
        .absoluteFilePath("tests/fixtures/analytic-muon-pair-event-v1.json"));
    if (!fixture.open(QIODevice::ReadOnly)) {
        qFatal("could not open deterministic analytic event fixture");
    }
    const QJsonDocument document = QJsonDocument::fromJson(fixture.readAll());
    if (!document.isObject()) {
        qFatal("deterministic analytic event fixture is not a JSON object");
    }
    return document.object();
}

int countTrajectoryColorPixels(const QImage& image)
{
    int count = 0;
    for (int y = 0; y < image.height(); ++y) {
        for (int x = 0; x < image.width(); ++x) {
            const QColor color = image.pixelColor(x, y);
            const bool blueTrack = color.blue() > 175
                && color.blue() > color.red() * 1.25
                && color.blue() > color.green() * 1.1;
            const bool orangeTrack = color.red() > 180
                && color.green() > 95
                && color.red() > color.blue() * 1.35;
            if (blueTrack || orangeTrack) ++count;
        }
    }
    return count;
}

} // namespace

class MainWindowTests : public QObject {
    Q_OBJECT

private slots:
    void packagedAnalyticSimulation()
    {
        const QDir appDir(QCoreApplication::applicationDirPath());
        if (!QFileInfo::exists(appDir.filePath("worker/heplab-worker.exe"))) {
            QSKIP("Run this scenario from the Windows package smoke kit.");
        }
        QTemporaryDir projects;
        QVERIFY(projects.isValid());
        heplab::MainWindow window(nullptr, projects.path());
        window.show();
        auto* navigation = window.findChild<QListWidget*>("mainNavigation");
        auto* run = window.findChild<QPushButton*>("runExperiment");
        auto* particles = window.findChild<QTableWidget*>("eventParticles");
        QVERIFY(navigation && run && particles);
        navigation->setCurrentRow(1);
        QTRY_VERIFY_WITH_TIMEOUT(run->isEnabled(), 30000);
        QTest::mouseClick(run, Qt::LeftButton);
        QTRY_COMPARE_WITH_TIMEOUT(navigation->currentRow(), 2, 30000);
        QTRY_COMPARE(particles->rowCount(), 2);

        const ProjectStore store(projects.path());
        const QDir artifacts(store.activeProjectRoot() + "/artifacts");
        const QStringList results = artifacts.entryList({"*.json"}, QDir::Files);
        QCOMPARE(results.size(), 1);
        QFile result(artifacts.filePath(results.first()));
        QVERIFY(result.open(QIODevice::ReadOnly));
        const QJsonObject artifact = QJsonDocument::fromJson(result.readAll()).object();
        QCOMPARE(artifact.value("config").toObject().value("mode").toString(), QString("analytic"));
        QCOMPARE(artifact.value("analysis").toObject().value("events").toInt(), 1);
        QCOMPARE(artifact.value("tracks").toArray().size(), 2);
    }

    void liveScientificWorkspacesAndResize()
    {
        QTemporaryDir projects;
        QVERIFY(projects.isValid());
        const auto disabled = qgetenv("HEPLAB_DISABLE_WORKER_FOR_TESTS");
        qunsetenv("HEPLAB_DISABLE_WORKER_FOR_TESTS");
        const auto restore = qScopeGuard([disabled] {
            if (disabled.isNull()) qunsetenv("HEPLAB_DISABLE_WORKER_FOR_TESTS");
            else qputenv("HEPLAB_DISABLE_WORKER_FOR_TESTS", disabled);
        });
        heplab::MainWindow window(nullptr, projects.path());
        window.show();
        auto* navigation = window.findChild<QListWidget*>("mainNavigation");
        auto* pages = window.findChild<QStackedWidget*>();
        auto* run = window.findChild<QPushButton*>("runExperiment");
        auto* budget = window.findChild<QSpinBox*>("eventBudget");
        auto* view = window.findChild<DetectorViewport3D*>("eventViewport3D");
        auto* pin = window.findChild<QPushButton*>("pinRun");
        QVERIFY(navigation && pages && run && budget && view && pin);
        QTRY_VERIFY_WITH_TIMEOUT(run->isEnabled(), 30000);
        QCOMPARE(pages->count(), 7);
        navigation->setCurrentRow(1);
        auto* source = window.findChild<QComboBox*>("particleSource");
        QVERIFY(source && !budget->isEnabled());
        source->setCurrentIndex(source->findData("angular_sample"));
        QVERIFY(budget->isEnabled());
        budget->setValue(2);
        QTest::mouseClick(run, Qt::LeftButton);
        QTRY_COMPARE_WITH_TIMEOUT(pages->currentIndex(), 2, 30000);
        QTRY_VERIFY(view->openGLAvailable());
        QCOMPARE(view->trackCount(), 2);
        auto* next = window.findChild<QPushButton*>("nextEvent");
        QVERIFY(next && next->isEnabled());
        QTest::mouseClick(next, Qt::LeftButton);
        QTRY_COMPARE(view->trackCount(), 2);
        QVERIFY(!next->isEnabled());
        auto* runs = window.findChild<QTableWidget*>("projectRuns");
        auto* catalog = window.findChild<QListWidget*>("cmsDatasets");
        auto* lessons = window.findChild<QListWidget*>("learningLessons");
        auto* validation = window.findChild<QTextBrowser*>("validationReport");
        auto* summary = window.findChild<QTextBrowser*>("experimentResult");
        QVERIFY(runs && catalog && lessons && validation && summary);
        QTRY_VERIFY(runs->rowCount() > 0);
        QTRY_VERIFY(catalog->count() > 0);
        QTRY_VERIFY(validation->toPlainText().contains("Maximum vector residual"));
        QVERIFY(summary->toPlainText().contains("Trajectory segments"));
        QVERIFY(lessons->count() > 0);
        catalog->setCurrentRow(0);
        lessons->setCurrentRow(0);
        navigation->setCurrentRow(4);
        QVERIFY(pin->isEnabled());
        QTest::mouseClick(pin, Qt::LeftButton);
        const auto plots = pages->widget(4)->findChildren<ScientificPlotWidget*>();
        QCOMPARE(plots.size(), 2);
        for (auto* plot : plots) QVERIFY(plot->isVisible());
        navigation->setCurrentRow(1);
        auto* momentum = window.findChild<QDoubleSpinBox*>("muonMomentum");
        QVERIFY(momentum);
        momentum->setValue(30.0);
        QTest::mouseClick(run, Qt::LeftButton);
        QTRY_COMPARE_WITH_TIMEOUT(pages->currentIndex(), 2, 30000);
        QTRY_COMPARE(runs->rowCount(), 2);
        QCOMPARE(view->trackCount(), 2);
        auto* particles = window.findChild<QTableWidget*>("eventParticles");
        QVERIFY(particles);
        particles->selectRow(0);
        QCOMPARE(view->selectedObjectId(), particles->item(0, 0)->text().toInt());
        for (auto* plot : plots) QVERIFY(plot->setAxisRange(0.0, 100.0));

        const auto capturePath = qEnvironmentVariable("HEPLAB_WORKSPACE_CAPTURES");
        if (!capturePath.isEmpty()) QVERIFY(QDir().mkpath(capturePath));
        const QStringList filenames{"projects", "simulation", "event-inspector",
            "cms-open-data", "runs-comparisons", "validation", "learn-heplab"};
        for (int index = 0; index < pages->count(); ++index) {
            navigation->setCurrentRow(index);
            for (const QSize size : {QSize(1024, 720), QSize(1280, 820)}) {
                window.resize(size);
                QCoreApplication::processEvents();
                QCOMPARE(pages->currentIndex(), index);
                QCOMPARE(window.size(), size);
                QVERIFY(pages->currentWidget()->isVisible());
            }
            if (!capturePath.isEmpty()) {
                const QString filename = QDir(capturePath).filePath(filenames.at(index) + ".png");
                QVERIFY2(window.grab().save(filename, "PNG"), qPrintable(filename));
            }
        }
    }

    void liveGeneratedCollisionAndAnalysis()
    {
        if (qEnvironmentVariableIsEmpty("HEPLAB_TEST_COLLISION_RUNTIME"))
            QSKIP("Set HEPLAB_TEST_COLLISION_RUNTIME with the pinned PYTHIA8 / DELPHES runtime.");
        QTemporaryDir projects;
        QVERIFY(projects.isValid());
        heplab::MainWindow window(nullptr, projects.path());
        window.show();
        auto* navigation = window.findChild<QListWidget*>("mainNavigation");
        auto* experiment = window.findChild<QComboBox*>("simulationExperiment");
        auto* budget = window.findChild<QSpinBox*>("eventBudget");
        auto* run = window.findChild<QPushButton*>("runExperiment");
        auto* next = window.findChild<QPushButton*>("nextEvent");
        auto* viewport = window.findChild<DetectorViewport3D*>("eventViewport3D");
        auto* objects = window.findChild<QTableWidget*>("eventParticles");
        auto* pin = window.findChild<QPushButton*>("pinRun");
        QVERIFY(navigation && experiment && budget && run && next && viewport && objects && pin);
        QTRY_VERIFY_WITH_TIMEOUT(run->isEnabled(), 30000);
        navigation->setCurrentRow(1);
        experiment->setCurrentIndex(1);
        budget->setValue(3);
        QTest::mouseClick(run, Qt::LeftButton);
        QTRY_COMPARE_WITH_TIMEOUT(navigation->currentRow(), 2, 120000);
        QTRY_VERIFY(viewport->openGLAvailable());
        QVERIFY(viewport->trackCount() > 2);
        QVERIFY(objects->rowCount() > viewport->trackCount());
        QVERIFY(next->isEnabled());
        qInfo() << "Collision event objects:" << objects->rowCount()
                << "generated trajectories:" << viewport->trackCount();
        QTest::mouseClick(next, Qt::LeftButton);
        QTRY_VERIFY_WITH_TIMEOUT(next->isEnabled(), 10000);
        QVERIFY(viewport->trackCount() > 2);

        navigation->setCurrentRow(4);
        QVERIFY(pin->isEnabled());
        pin->click();
        const auto plots = window.findChildren<ScientificPlotWidget*>();
        QCOMPARE(plots.size(), 2);
        auto* observable = window.findChild<QComboBox*>("runObservable");
        auto* cutflow = window.findChild<QTableWidget*>("collisionCutflow");
        QVERIFY(observable && cutflow);
        observable->setCurrentIndex(4);
        for (auto* plot : plots)
            QVERIFY(plot->accessibleDescription().startsWith("3 samples"));
        QCOMPARE(cutflow->rowCount(), 5);
        QCOMPARE(cutflow->item(0, 1)->text(), QString("3"));
        QCOMPARE(cutflow->item(0, 4)->text(), QString("3"));
    }

    void workspaceCommandsAndAppearance()
    {
        const QString previousName = QApplication::applicationName();
        QApplication::setApplicationName("HEPLabWorkspaceUiTest");
        QSettings().setValue("appearance/dark", true);
        QSettings().setValue("appearance/compact", false);
        {
            heplab::MainWindow window;
            auto* navigation = window.findChild<QListWidget*>("mainNavigation");
            QVERIFY(navigation);
            QAction* inspector = nullptr;
            QAction* dark = nullptr;
            QAction* palette = nullptr;
            for (auto* action : window.findChildren<QAction*>()) {
                if (action->text() == "Event Inspector") inspector = action;
                if (action->text() == "Dark theme") dark = action;
                if (action->shortcut() == QKeySequence("Ctrl+K")) palette = action;
            }
            QVERIFY(inspector && dark && palette);
            inspector->trigger();
            QCOMPARE(navigation->currentRow(), 2);
            const QColor before = qApp->palette().color(QPalette::Window);
            dark->trigger();
            QVERIFY(qApp->palette().color(QPalette::Window) != before);
            QCOMPARE(QSettings().value("appearance/dark").toBool(), false);
            window.resize(1024, 720);
            QVERIFY(window.minimumSizeHint().width() <= 1024);
        }
        QApplication::setApplicationName(previousName);
    }
    void createsNativeShell()
    {
        heplab::MainWindow window;
        QCOMPARE(window.windowTitle(), QString("HEPLab Workbench"));
        QVERIFY(window.centralWidget() != nullptr);
        QVERIFY(window.statusBar() != nullptr);
    }

    void navigationHasSevenScientificSections()
    {
        heplab::MainWindow window;
        auto* navigation = window.findChild<QListWidget*>("mainNavigation");
        auto* pages = window.findChild<QStackedWidget*>();
        QVERIFY(navigation != nullptr);
        QVERIFY(pages != nullptr);
        QCOMPARE(navigation->count(), 7);
        QCOMPARE(pages->count(), 7);

        const QStringList expected = {
            "Home / Projects",
            "Simulation",
            "Event Inspector",
            "CMS Open Data",
            "Runs / Comparisons",
            "Validation",
            "Learning / Documentation",
        };
        for (int index = 0; index < expected.size(); ++index) {
            QCOMPARE(navigation->item(index)->text(), expected.at(index));
        }

        navigation->setCurrentRow(2);
        QCoreApplication::processEvents();
        QCOMPARE(pages->currentIndex(), 2);
    }

    void writesRepresentativeSimulationScreenshot()
    {
        heplab::MainWindow window;
        auto* navigation = window.findChild<QListWidget*>("mainNavigation");
        auto* pages = window.findChild<QStackedWidget*>();
        QVERIFY(navigation != nullptr);
        QVERIFY(pages != nullptr);
        navigation->setCurrentRow(1);
        QCoreApplication::processEvents();
        window.resize(1280, 820);
        window.show();
        QCoreApplication::processEvents();

        const QString directory =
            QDir(QT_TESTCASE_SOURCEDIR).absoluteFilePath("../output/native-rebuild");
        QVERIFY(QDir().mkpath(directory));
        const QString path = directory + "/native-shell-simulation.png";
        QVERIFY(window.grab().save(path, "PNG"));
        QVERIFY(QFileInfo::exists(path));
    }

    void projectStoreCreatesRenamesSavesAndReopens()
    {
        QTemporaryDir root;
        QVERIFY(root.isValid());
        ProjectStore store(root.path() + "/projects");

        const QString projectId =
            store.createProject("Reproducibility Test");
        QVERIFY(!projectId.isEmpty());
        QCOMPARE(store.activeProjectId(), projectId);
        QVERIFY(!store.activeProjectRoot().isEmpty());
        QVERIFY(store.renameProject(projectId, "Renamed Project"));

        QJsonObject configuration;
        configuration["seed"] = 42;
        configuration["events"] = 1;
        configuration["momentum_gev"] = 45.0;
        QVERIFY(store.saveProject(projectId, configuration, "aabbcc"));

        ProjectStore reopened(root.path() + "/projects");
        QVERIFY(reopened.openProject(projectId));
        QCOMPARE(reopened.project(projectId).value("name").toString(),
                 QString("Renamed Project"));
        QCOMPARE(reopened.project(projectId).value("last_run_id").toString(),
                 QString("aabbcc"));

        const QString manifestPath =
            reopened.activeProjectRoot() + "/project.json";
        QFile manifest(manifestPath);
        QVERIFY(manifest.open(QIODevice::ReadOnly));
        const QJsonObject saved =
            QJsonDocument::fromJson(manifest.readAll()).object();
        QCOMPARE(saved.value("schema").toString(),
                 QString("heplab-native-project-v1"));
        QCOMPARE(saved.value("configuration").toObject().value("seed").toInt(),
                 42);
        const QJsonArray runIds = saved.value("run_ids").toArray();
        QCOMPARE(runIds.size(), 1);
        QCOMPARE(runIds.at(0).toString(), QString("aabbcc"));
    }

    void eventAdapterValidatesSchemaUnitsAndIdentity()
    {
        const QJsonObject source = analyticFixture();
        const heplab::EventData event = heplab::EventDataAdapter::fromJson(source);
        QVERIFY2(event.valid, qPrintable(event.diagnostic));
        QCOMPARE(event.eventIndex, 0);
        QCOMPARE(event.tracks.size(), 2);
        QVERIFY(event.tracks.at(0).kind
                == heplab::DisplayObjectKind::GeneratedParticle);
        QVERIFY(!event.tracks.at(0).stableIdentity.isEmpty());
        QVERIFY(event.tracks.at(0).stableIdentity
                != event.tracks.at(1).stableIdentity);
        QCOMPARE(event.trajectorySegmentCount(), 652);

        const QJsonArray sourceTracks = source.value("tracks").toArray();
        for (int trackIndex = 0; trackIndex < sourceTracks.size(); ++trackIndex) {
            const QJsonArray sourcePoints = sourceTracks.at(trackIndex)
                .toObject().value("points").toArray();
            const auto& typedPoints = event.tracks.at(trackIndex).positionsM;
            QCOMPARE(typedPoints.size(), sourcePoints.size());
            for (int pointIndex = 0; pointIndex < sourcePoints.size(); ++pointIndex) {
                const QJsonArray point = sourcePoints.at(pointIndex).toArray();
                QVERIFY(std::abs(typedPoints.at(pointIndex).xM - point.at(0).toDouble()) < 1e-12);
                QVERIFY(std::abs(typedPoints.at(pointIndex).yM - point.at(1).toDouble()) < 1e-12);
                QVERIFY(std::abs(typedPoints.at(pointIndex).zM - point.at(2).toDouble()) < 1e-12);
            }
        }

        QJsonObject badUnits = source;
        QJsonObject geometry = badUnits.value("geometry").toObject();
        geometry["units"] = "millimetres";
        badUnits["geometry"] = geometry;
        const heplab::EventData unitsResult = heplab::EventDataAdapter::fromJson(badUnits);
        QVERIFY(!unitsResult.valid);
        QVERIFY(unitsResult.diagnostic.contains("metres"));

        QJsonObject duplicateIdentity = source;
        QJsonArray duplicateTracks = duplicateIdentity.value("tracks").toArray();
        QJsonObject duplicateTrack = duplicateTracks.at(1).toObject();
        duplicateTrack["object_id"] = duplicateTracks.at(0).toObject()
            .value("object_id").toInt();
        duplicateTracks[1] = duplicateTrack;
        duplicateIdentity["tracks"] = duplicateTracks;
        const heplab::EventData duplicateResult =
            heplab::EventDataAdapter::fromJson(duplicateIdentity);
        QVERIFY(!duplicateResult.valid);
        QVERIFY(duplicateResult.diagnostic.contains("duplicated"));

        QJsonObject malformedPoints = source;
        QJsonArray malformedTracks = malformedPoints.value("tracks").toArray();
        QJsonObject malformedTrack = malformedTracks.at(0).toObject();
        QJsonArray points = malformedTrack.value("points").toArray();
        points[4] = QJsonArray{1.0, 2.0};
        malformedTrack["points"] = points;
        malformedTracks[0] = malformedTrack;
        malformedPoints["tracks"] = malformedTracks;
        const heplab::EventData malformedResult =
            heplab::EventDataAdapter::fromJson(malformedPoints);
        QVERIFY(!malformedResult.valid);
        QVERIFY(malformedResult.diagnostic.contains("x_m, y_m, z_m"));

        QJsonObject noTracks = source;
        noTracks.remove("tracks");
        const heplab::EventData missingTracks =
            heplab::EventDataAdapter::fromJson(noTracks);
        QVERIFY(!missingTracks.valid);
        QVERIFY(missingTracks.diagnostic.contains("tracks"));

        QJsonObject reconstructed = source;
        QJsonArray reconstructedTracks = reconstructed.value("tracks").toArray();
        QJsonObject reconstructedTrack = reconstructedTracks.at(0).toObject();
        reconstructedTrack["truth"] = QJsonObject();
        reconstructedTrack["detector"] = QJsonObject{
            {"pt", 41.5}, {"eta", 0.2}, {"phi", -0.7}};
        reconstructedTracks[0] = reconstructedTrack;
        reconstructed["tracks"] = reconstructedTracks;
        const heplab::EventData reconstructedEvent =
            heplab::EventDataAdapter::fromJson(reconstructed);
        QVERIFY(reconstructedEvent.valid);
        QVERIFY(reconstructedEvent.tracks.at(0).kind
                == heplab::DisplayObjectKind::ReconstructedObject);
        QCOMPARE(reconstructedEvent.tracks.at(0).reconstructedPtGeV.value(), 41.5);
    }

    void projectionsUseCorrectAxesUnitsFitAndZoom()
    {
        const heplab::Position3M position{1.25, -2.5, 4.0};
        QCOMPARE(EventProjectionWidget::projectPosition(
                     position, EventProjectionWidget::Projection::XY),
                 QPointF(1.25, -2.5));
        QCOMPARE(EventProjectionWidget::projectPosition(
                     position, EventProjectionWidget::Projection::XZ),
                 QPointF(4.0, 1.25));

        const heplab::EventData event =
            heplab::EventDataAdapter::fromJson(analyticFixture());
        QVERIFY(event.valid);
        EventProjectionWidget xy(EventProjectionWidget::Projection::XY);
        EventProjectionWidget xz(EventProjectionWidget::Projection::XZ);
        xy.resize(640, 380);
        xz.resize(640, 380);
        xy.setEvent(event);
        xz.setEvent(event);
        xy.show();
        xz.show();
        QCoreApplication::processEvents();
        QCOMPARE(xy.trackCount(), 2);
        QCOMPARE(xz.trackCount(), 2);
        QCOMPARE(xy.visibleSegmentCount(), 652);
        QCOMPARE(xz.visibleSegmentCount(), 652);
        QVERIFY(xy.sceneRadiusMetres() > 15.0);
        QVERIFY(xz.sceneRadiusMetres() > 15.0);
        QVERIFY(xy.labelForObject(0).contains("Generated particle"));
        QVERIFY(countTrajectoryColorPixels(xy.grab().toImage()) > 30);
        QVERIFY(countTrajectoryColorPixels(xz.grab().toImage()) > 30);

        QWheelEvent zoomIn(QPointF(xy.rect().center()),
                           QPointF(xy.mapToGlobal(xy.rect().center())),
                           QPoint(), QPoint(0, 120), Qt::NoButton,
                           Qt::NoModifier, Qt::NoScrollPhase, false);
        QCoreApplication::sendEvent(&xy, &zoomIn);
        QVERIFY(xy.zoomFactor() > 1.0);
        const QPointF oldPan = xy.panOffsetMetres();
        QTest::mousePress(&xy, Qt::RightButton, Qt::NoModifier, QPoint(320, 180));
        QTest::mouseMove(&xy, QPoint(350, 205));
        QTest::mouseRelease(&xy, Qt::RightButton, Qt::NoModifier, QPoint(350, 205));
        QVERIFY(xy.panOffsetMetres() != oldPan);

        xy.fitView();
        QCOMPARE(xy.zoomFactor(), 1.0);
        QCOMPARE(xy.panOffsetMetres(), QPointF());
    }

    void threeDViewportPopulatesSwitchesAndClearsEvents()
    {
        const QJsonObject fixture = analyticFixture();
        const heplab::EventData event = heplab::EventDataAdapter::fromJson(fixture);
        QVERIFY(event.valid);

        DetectorViewport3D view;
        view.resize(640, 420);
        view.show();
        view.setEvent(event);
        QTRY_VERIFY_WITH_TIMEOUT(view.openGLAvailable(), 8000);
        QCOMPARE(view.trackCount(), 2);
        QCOMPARE(view.visibleSegmentCount(), 652);
        view.setGeometryVisible(false);
        QCOMPARE(view.visibleSegmentCount(), 652);
        view.setTrajectoriesVisible(false);
        QCOMPARE(view.visibleSegmentCount(), 0);
        view.setTrajectoriesVisible(true);
        QCOMPARE(view.visibleSegmentCount(), 652);
        QVERIFY(countTrajectoryColorPixels(view.grab().toImage()) > 20);

        view.setSelectedObjectId(0);
        QCOMPARE(view.selectedObjectId(), 0);
        view.resetCamera();
        QCOMPARE(view.selectedObjectId(), 0);

        QJsonObject nextEventJson = fixture;
        nextEventJson["event"] = 1;
        QJsonArray oneTrack{fixture.value("tracks").toArray().at(1)};
        nextEventJson["tracks"] = oneTrack;
        const heplab::EventData nextEvent =
            heplab::EventDataAdapter::fromJson(nextEventJson);
        QVERIFY(nextEvent.valid);
        view.setEvent(nextEvent);
        QCOMPARE(view.trackCount(), 1);
        QCOMPARE(view.visibleSegmentCount(), 326);
        QCOMPARE(view.selectedObjectId(), -1);
        view.clearEvent("Event cleared for the next run.");
        QCOMPARE(view.trackCount(), 0);
        QCOMPARE(view.visibleSegmentCount(), 0);
    }

    void cameraOrbitZoomPanAndReset()
    {
        const heplab::EventData event =
            heplab::EventDataAdapter::fromJson(analyticFixture());
        DetectorViewport3D view;
        view.resize(640, 420);
        view.show();
        view.setEvent(event);
        QTRY_VERIFY_WITH_TIMEOUT(view.openGLAvailable(), 8000);
        const auto before = view.cameraState();

        QTest::mousePress(&view, Qt::LeftButton, Qt::NoModifier, QPoint(280, 180));
        QTest::mouseMove(&view, QPoint(330, 210));
        QTest::mouseRelease(&view, Qt::LeftButton, Qt::NoModifier, QPoint(330, 210));
        const auto orbited = view.cameraState();
        QVERIFY(orbited.azimuthDegrees != before.azimuthDegrees);
        QVERIFY(orbited.elevationDegrees != before.elevationDegrees);

        QWheelEvent zoomIn(QPointF(view.rect().center()),
                           QPointF(view.mapToGlobal(view.rect().center())),
                           QPoint(), QPoint(0, 120), Qt::NoButton,
                           Qt::NoModifier, Qt::NoScrollPhase, false);
        QCoreApplication::sendEvent(&view, &zoomIn);
        const auto zoomed = view.cameraState();
        QVERIFY(zoomed.distanceScale < orbited.distanceScale);

        QTest::mousePress(&view, Qt::RightButton, Qt::NoModifier, QPoint(300, 200));
        QTest::mouseMove(&view, QPoint(330, 225));
        QTest::mouseRelease(&view, Qt::RightButton, Qt::NoModifier, QPoint(330, 225));
        QVERIFY(view.cameraState().targetM != zoomed.targetM);

        view.resetCamera();
        const auto reset = view.cameraState();
        QCOMPARE(reset.azimuthDegrees, 35.0f);
        QCOMPARE(reset.elevationDegrees, 25.0f);
        QCOMPARE(reset.distanceScale, 4.2f);
        QCOMPARE(reset.targetM, before.targetM);
    }

    void selectionAndEventSwitchingStaySynchronized()
    {
        const QJsonObject fixture = analyticFixture();
        const heplab::EventData event = heplab::EventDataAdapter::fromJson(fixture);
        QVERIFY(event.valid);

        heplab::MainWindow window;
        window.resize(1600, 940);
        window.show();
        auto* navigation = window.findChild<QListWidget*>("mainNavigation");
        const auto projections = window.findChildren<EventProjectionWidget*>();
        QCOMPARE(projections.size(), 2);
        auto* viewLayout = window.findChild<QComboBox*>("eventViewLayout");
        QVERIFY(viewLayout);
        auto* view3D = window.findChild<DetectorViewport3D*>("eventViewport3D");
        auto* table = window.findChild<QTableWidget*>("eventParticles");
        auto* properties = window.findChild<QTextEdit*>("eventProperties");
        auto* frame = window.findChild<QPushButton*>("frameSelectedTrack");
        QVERIFY(navigation && view3D && table && properties && frame);
        navigation->setCurrentRow(2);
        window.setInspectorEvent(fixture);
        QTRY_VERIFY_WITH_TIMEOUT(view3D->openGLAvailable(), 8000);
        QCOMPARE(viewLayout->currentIndex(), 3);
        for (auto* projection : projections) QVERIFY(projection->isVisible());
        viewLayout->setCurrentIndex(0);
        for (auto* projection : projections) QVERIFY(!projection->isVisible());
        viewLayout->setCurrentIndex(3);
        for (auto* projection : projections) QVERIFY(projection->isVisible());
        QCOMPARE(table->rowCount(), 2);

        QVERIFY(!frame->isEnabled());
        const auto beforeFrame = view3D->cameraState();
        table->selectRow(0);
        QVERIFY(frame->isEnabled());
        frame->click();
        const auto afterFrame = view3D->cameraState();
        QVERIFY(afterFrame.targetM != beforeFrame.targetM);
        QCOMPARE(afterFrame.azimuthDegrees, beforeFrame.azimuthDegrees);
        QCOMPARE(view3D->selectedObjectId(), 0);
        for (auto* projection : projections) QCOMPARE(projection->selectedObjectId(), 0);
        QVERIFY(properties->toPlainText().contains("Stable identity:"));
        QVERIFY(properties->toPlainText().contains("Momentum [GeV/c]:"));

        QVERIFY(QMetaObject::invokeMethod(view3D, "objectSelected",
            Qt::DirectConnection, Q_ARG(int, 1)));
        QCOMPARE(view3D->selectedObjectId(), 1);
        QCOMPARE(table->selectedItems().first()->text(), QString("1"));

        QJsonObject secondEvent = fixture;
        secondEvent["event"] = 1;
        QJsonArray singleTrack{fixture.value("tracks").toArray().at(1)};
        secondEvent["tracks"] = singleTrack;
        window.setInspectorEvent(secondEvent);
        QCOMPARE(view3D->selectedObjectId(), -1);
        QVERIFY(!frame->isEnabled());
        QCOMPARE(table->rowCount(), 1);
        QCOMPARE(view3D->visibleSegmentCount(), 326);

        // Collision mode exposes Origin column, PDG species label, and event_info overview.
        QJsonObject collision = fixture;
        collision["mode"] = "pythia";
        collision["event_info"] = QJsonObject{
            {"event", 0}, {"weight", 1.5}, {"muons", 2}, {"jets", 1},
            {"met_gev", 12.3}, {"selected", true}, {"mass_gev", 91.2},
        };
        window.setInspectorEvent(collision);
        QVERIFY(!table->isColumnHidden(5));
        QVERIFY(table->item(0, 2)->text().contains("μ"));
        QVERIFY(properties->toPlainText().contains("PYTHIA8 / DELPHES"));
        QVERIFY(properties->toPlainText().contains("91.2"));
    }

    void scientificPlotUsesOnlyArtifactNumericalValues()
    {
        QJsonObject result;
        QJsonObject analysis;
        QJsonArray pairs;
        QJsonObject pair;
        pair["truth_mass_gev"] = 90.0;
        pairs.append(pair);
        analysis["pairs"] = pairs;
        QJsonArray samples;
        QJsonObject sample;
        sample["pt_gev"] = 45.0;
        samples.append(sample);
        analysis["samples"] = samples;
        result["analysis"] = analysis;

        ScientificPlotWidget plot;
        plot.resize(800, 400);
        plot.setResult(result);
        plot.setObservable(ScientificPlotWidget::Observable::InvariantMass);
        QCOMPARE(plot.populatedBinCount(), 1);
        QCOMPARE(plot.eventCount(), 1);
        const auto rows = plot.binRows();
        QCOMPARE(rows.size(), 24);
        double normSum = 0.0;
        for (const auto& r : rows) normSum += r.normalized;
        QVERIFY(std::abs(normSum - 1.0) < 1e-6);
        QVERIFY(std::abs(rows.last().cumulative - 1.0) < 1e-6);
        QImage image = plot.grab().toImage();
        QVERIFY(!image.isNull());
        plot.setGraphMode(ScientificPlotWidget::GraphMode::NormalizedShape);
        QVERIFY(!plot.grab().toImage().isNull());
        plot.setGraphMode(ScientificPlotWidget::GraphMode::Cumulative);
        QVERIFY(!plot.grab().toImage().isNull());
        plot.setObservable(ScientificPlotWidget::Observable::MuonPt);
        QImage momentum = plot.grab().toImage();
        QVERIFY(!momentum.isNull());

        QTemporaryDir project;
        QVERIFY(project.isValid());
        heplab::MainWindow window(nullptr, project.path());
        auto* binTable = window.findChild<QTableWidget*>("runBinTable");
        auto* graphMode = window.findChild<QComboBox*>("runGraphMode");
        QVERIFY(binTable != nullptr);
        QVERIFY(graphMode != nullptr);
        QCOMPARE(graphMode->count(), 4);
        QCOMPARE(binTable->rowCount(), 24);
    }

    void cmsCatalogIsManifestBackedAndNotPhysicsValidated()
    {
        QTemporaryDir project;
        QVERIFY(project.isValid());
        WorkerClient worker;
        QSignalSpy handshake(&worker, &WorkerClient::handshakeReceived);
        const QString repositoryRoot =
            QDir(QT_TESTCASE_SOURCEDIR).absoluteFilePath("..");
        worker.start(repositoryRoot, project.path());
        QVERIFY(handshake.wait(60000));

        QSignalSpy response(&worker, &WorkerClient::responseReceived);
        QVERIFY(worker.sendRequest("datasets.list") > 0);
        QVERIFY(response.wait(60000));
        const QJsonObject reply =
            response.first().at(1).value<QJsonObject>();
        QVERIFY(reply.value("ok").toBool());
        QVERIFY(reply.value("result").isArray());
        for (const auto& value : reply.value("result").toArray()) {
            const QJsonObject manifest = value.toObject();
            QVERIFY(manifest.contains("name"));
            QVERIFY(manifest.contains("record"));
            QVERIFY(manifest.contains("certification"));
        }
        worker.stop();
    }

    void workerHandshakeRejectsInvalidConfigAndCompletesAnalyticRun()
    {
        QTemporaryDir project;
        QVERIFY(project.isValid());

        WorkerClient worker;
        QSignalSpy handshake(&worker, &WorkerClient::handshakeReceived);
        const QString repositoryRoot =
            QDir(QT_TESTCASE_SOURCEDIR).absoluteFilePath("..");
        worker.start(repositoryRoot, project.path());
        QVERIFY(handshake.wait(60000));
        QVERIFY(worker.isRunning());

        QJsonObject badConfig;
        badConfig["mode"] = "analytic";
        badConfig["executable"] = "cmd.exe";
        QJsonObject badArgs;
        badArgs["config"] = badConfig;
        badArgs["idempotency_key"] = "bad-config-1";
        QSignalSpy badResponse(&worker, &WorkerClient::responseReceived);
        QVERIFY(worker.sendRequest("jobs.submit", badArgs) > 0);
        QVERIFY(badResponse.wait(60000));
        const QJsonObject badReply =
            badResponse.first().at(1).value<QJsonObject>();
        QVERIFY(!badReply.value("ok").toBool());

        QJsonObject config;
        config["mode"] = "analytic";
        config["backend"] = "reference";
        config["seed"] = 42;
        config["events"] = 1;
        config["momentum_gev"] = 45.0;
        config["bz_tesla"] = 3.8;
        config["thickness_mm"] = 1.0;
        config["response_model"] = "ideal";
        config["field_model"] = "ideal_bore";
        config["source_model"] = "transverse_pair";
        QJsonObject submitArgs;
        submitArgs["config"] = config;
        submitArgs["idempotency_key"] = "native-slice-1";
        QSignalSpy submitResponse(&worker, &WorkerClient::responseReceived);
        worker.sendRequest("jobs.submit", submitArgs);
        QVERIFY(submitResponse.wait(60000));
        const QJsonObject submitReply =
            submitResponse.first().at(1).value<QJsonObject>();
        QVERIFY(submitReply.value("ok").toBool());
        const QString runId =
            submitReply.value("result").toObject().value("id").toString();
        QVERIFY(!runId.isEmpty());

        QString status;
        for (int attempt = 0; attempt < 600; ++attempt) {
            QJsonObject getArgs;
            getArgs["job_id"] = runId;
            QSignalSpy getResponse(&worker, &WorkerClient::responseReceived);
            worker.sendRequest("jobs.get", getArgs);
            QVERIFY(getResponse.wait(60000));
            const QJsonObject getReply =
                getResponse.first().at(1).value<QJsonObject>();
            status = getReply.value("result").toObject().value("status").toString();
            if (status == "completed" || status == "failed" || status == "cancelled") {
                break;
            }
            QTest::qWait(50);
        }
        QCOMPARE(status, QString("completed"));

        QJsonObject eventArgs;
        eventArgs["job_id"] = runId;
        eventArgs["index"] = 0;
        QSignalSpy eventResponse(&worker, &WorkerClient::responseReceived);
        worker.sendRequest("jobs.event", eventArgs);
        QVERIFY(eventResponse.wait(60000));
        const QJsonObject eventReply =
            eventResponse.first().at(1).value<QJsonObject>();
        QVERIFY(eventReply.value("ok").toBool());
        const QJsonObject backendEvent = eventReply.value("result").toObject();
        QCOMPARE(backendEvent.value("geometry").toObject()
                     .value("units").toString(), QString("metres"));
        const heplab::EventData displayedEvent =
            heplab::EventDataAdapter::fromJson(backendEvent);
        QVERIFY2(displayedEvent.valid, qPrintable(displayedEvent.diagnostic));
        QCOMPARE(displayedEvent.tracks.size(), 2);
        QCOMPARE(displayedEvent.trajectorySegmentCount(), 652);
        const QJsonArray backendTracks = backendEvent.value("tracks").toArray();
        for (int trackIndex = 0; trackIndex < backendTracks.size(); ++trackIndex) {
            const QJsonArray sourcePoints = backendTracks.at(trackIndex)
                .toObject().value("points").toArray();
            QCOMPARE(displayedEvent.tracks.at(trackIndex).positionsM.size(),
                     sourcePoints.size());
            for (int pointIndex = 0; pointIndex < sourcePoints.size(); ++pointIndex) {
                const QJsonArray point = sourcePoints.at(pointIndex).toArray();
                const auto& converted = displayedEvent.tracks.at(trackIndex)
                    .positionsM.at(pointIndex);
                QVERIFY(std::abs(converted.xM - point.at(0).toDouble()) < 1e-12);
                QVERIFY(std::abs(converted.yM - point.at(1).toDouble()) < 1e-12);
                QVERIFY(std::abs(converted.zM - point.at(2).toDouble()) < 1e-12);
            }
        }
        QVERIFY(QFileInfo::exists(
            project.path() + "/artifacts/" + runId + ".json"));
        worker.stop();
    }

    void workerCancellationDoesNotPublishCompletedRun()
    {
        QTemporaryDir project;
        QVERIFY(project.isValid());
        WorkerClient worker;
        QSignalSpy handshake(&worker, &WorkerClient::handshakeReceived);
        const QString repositoryRoot =
            QDir(QT_TESTCASE_SOURCEDIR).absoluteFilePath("..");
        worker.start(repositoryRoot, project.path());
        QVERIFY(handshake.wait(60000));

        QJsonObject config;
        config["mode"] = "analytic";
        config["backend"] = "reference";
        config["seed"] = 43;
        config["events"] = 100;
        config["momentum_gev"] = 45.0;
        config["bz_tesla"] = 3.8;
        config["thickness_mm"] = 1.0;
        config["response_model"] = "ideal";
        config["field_model"] = "ideal_bore";
        config["source_model"] = "angular_sample";
        QJsonObject submitArgs;
        submitArgs["config"] = config;
        submitArgs["idempotency_key"] = "native-cancel-1";
        QSignalSpy submitResponse(&worker, &WorkerClient::responseReceived);
        worker.sendRequest("jobs.submit", submitArgs);
        QVERIFY(submitResponse.wait(60000));
        const QString runId =
            submitResponse.first().at(1).value<QJsonObject>()
                .value("result").toObject().value("id").toString();
        QVERIFY(!runId.isEmpty());

        QJsonObject cancelArgs;
        cancelArgs["job_id"] = runId;
        QSignalSpy cancelResponse(&worker, &WorkerClient::responseReceived);
        worker.sendRequest("jobs.cancel", cancelArgs);
        QVERIFY(cancelResponse.wait(60000));

        QString status;
        for (int attempt = 0; attempt < 600; ++attempt) {
            QJsonObject getArgs;
            getArgs["job_id"] = runId;
            QSignalSpy getResponse(&worker, &WorkerClient::responseReceived);
            worker.sendRequest("jobs.get", getArgs);
            QVERIFY(getResponse.wait(60000));
            status = getResponse.first().at(1).value<QJsonObject>()
                         .value("result").toObject().value("status").toString();
            if (status == "cancelled" || status == "completed" || status == "failed") {
                break;
            }
            QTest::qWait(50);
        }
        QCOMPARE(status, QString("cancelled"));
        QVERIFY(!QFileInfo::exists(
            project.path() + "/artifacts/" + runId + ".json"));
        worker.stop();
    }
};

int main(int argc, char* argv[])
{
    QApplication app(argc, argv);
    QApplication::setOrganizationName("HEPLabTests");
    QTemporaryDir settingsDir;
    if (!settingsDir.isValid()) return 1;
    QSettings::setDefaultFormat(QSettings::IniFormat);
    QSettings::setPath(QSettings::IniFormat, QSettings::UserScope, settingsDir.path());
    MainWindowTests tests;
    return QTest::qExec(&tests, argc, argv);
}

#include "MainWindowTests.moc"
