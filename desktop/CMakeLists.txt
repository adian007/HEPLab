add_library(heplab_desktop_core
    src/Application.cpp
    src/MainWindow.cpp
    src/ResearchCatalogs.cpp
    src/WorkerClient.cpp
    src/ProjectStore.cpp
    src/EventData.cpp
    src/EventProjectionWidget.cpp
    src/DetectorViewport3D.cpp
    src/ScientificPlotWidget.cpp
)

target_include_directories(heplab_desktop_core PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/src
)

target_link_libraries(heplab_desktop_core PUBLIC
    Qt6::Core
    Qt6::Gui
    Qt6::Widgets
    Qt6::OpenGL
    Qt6::OpenGLWidgets
)

add_executable(HEPLabWorkbench
    src/main.cpp
    resources/training.qrc
    resources/cms-muon.qrc
    resources/branding.qrc
    resources/app.rc
)

target_link_libraries(HEPLabWorkbench PRIVATE heplab_desktop_core)

if(HEPLAB_BUILD_TESTS)
    find_program(HEPLAB_UV_EXECUTABLE
        NAMES uv uv.exe
        HINTS
            "$ENV{LOCALAPPDATA}/Microsoft/WinGet/Links"
            "$ENV{USERPROFILE}/.local/bin"
    )
    if(NOT HEPLAB_UV_EXECUTABLE)
        message(WARNING "uv was not found; native worker tests will require HEPLAB_UV")
    endif()

    add_executable(heplab_desktop_tests
        tests/MainWindowTests.cpp
        resources/training.qrc
        resources/cms-muon.qrc
        resources/branding.qrc
    )
    target_link_libraries(heplab_desktop_tests PRIVATE
        heplab_desktop_core
        Qt6::Test
    )
    add_test(NAME heplab_native_shell COMMAND heplab_desktop_tests createsNativeShell)
    add_test(NAME heplab_workspace_commands COMMAND heplab_desktop_tests workspaceCommandsAndAppearance)
    add_test(NAME heplab_live_workspaces COMMAND heplab_desktop_tests liveScientificWorkspacesAndResize
        -o "${CMAKE_CURRENT_BINARY_DIR}/live-workspaces.log,txt")
    add_test(NAME heplab_native_navigation COMMAND heplab_desktop_tests navigationHasSevenScientificSections)
    add_test(NAME heplab_project_persistence COMMAND heplab_desktop_tests projectStoreCreatesRenamesSavesAndReopens)
    add_test(NAME heplab_event_adapter COMMAND heplab_desktop_tests eventAdapterValidatesSchemaUnitsAndIdentity)
    add_test(NAME heplab_2d_projection COMMAND heplab_desktop_tests projectionsUseCorrectAxesUnitsFitAndZoom)
    add_test(NAME heplab_3d_viewport COMMAND heplab_desktop_tests threeDViewportPopulatesSwitchesAndClearsEvents)
    add_test(NAME heplab_3d_camera COMMAND heplab_desktop_tests cameraOrbitZoomPanAndReset)
    add_test(NAME heplab_view_selection_sync COMMAND heplab_desktop_tests selectionAndEventSwitchingStaySynchronized)
    add_test(NAME heplab_scientific_plot COMMAND heplab_desktop_tests scientificPlotUsesOnlyArtifactNumericalValues)
    add_test(NAME heplab_cms_catalog COMMAND heplab_desktop_tests cmsCatalogIsManifestBackedAndNotPhysicsValidated)
    add_test(NAME heplab_worker_success COMMAND heplab_desktop_tests workerHandshakeRejectsInvalidConfigAndCompletesAnalyticRun)
    add_test(NAME heplab_worker_cancellation COMMAND heplab_desktop_tests workerCancellationDoesNotPublishCompletedRun)

    get_filename_component(QT_PREFIX "${Qt6_DIR}/../../../" ABSOLUTE)
    set_tests_properties(
        heplab_native_shell
        heplab_workspace_commands
        heplab_live_workspaces
        heplab_native_navigation
        heplab_project_persistence
        heplab_event_adapter
        heplab_2d_projection
        heplab_3d_viewport
        heplab_3d_camera
        heplab_view_selection_sync
        heplab_scientific_plot
        heplab_cms_catalog
        heplab_worker_success
        heplab_worker_cancellation
        PROPERTIES
        ENVIRONMENT "HEPLAB_DISABLE_WORKER_FOR_TESTS=1;HEPLAB_UV=${HEPLAB_UV_EXECUTABLE};HEPLAB_REPOSITORY_ROOT=${CMAKE_SOURCE_DIR}"
        ENVIRONMENT_MODIFICATION "PATH=path_list_prepend:${QT_PREFIX}/bin"
        TIMEOUT 180
    )
endif()
