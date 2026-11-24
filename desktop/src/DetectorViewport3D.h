#pragma once

#include "EventData.h"

#include <QOpenGLBuffer>
#include <QOpenGLFunctions>
#include <QOpenGLShaderProgram>
#include <QOpenGLVertexArrayObject>
#include <QOpenGLWidget>
#include <QPoint>
#include <QVector3D>

#include <memory>
#include <array>

class QMouseEvent;
class QMatrix4x4;
class QWheelEvent;

class DetectorViewport3D final : public QOpenGLWidget, protected QOpenGLFunctions {
    Q_OBJECT

public:
    enum class CameraPreset { Isometric, XY, XZ, YZ };
    enum class MuonLayer { DT, CSC, RPC };
    enum class CutawayAxis { X, Y, Z };
    struct CameraState {
        float azimuthDegrees = 35.0f;
        float elevationDegrees = 25.0f;
        float distanceScale = 4.2f;
        QVector3D targetM;
    };

    explicit DetectorViewport3D(QWidget* parent = nullptr);
    ~DetectorViewport3D() override;

    void setEvent(const heplab::EventData& event);
    void clearEvent(const QString& message);
    void setSelectedObjectId(int objectId);
    void setGeometryVisible(bool visible);
    void setGridVisible(bool visible);
    void setCrossingsVisible(bool visible);
    void setMuonLayerVisible(MuonLayer layer, bool visible);
    void setMuonLayerOpacity(MuonLayer layer, float opacity);
    void setMuonCutaway(bool enabled, CutawayAxis axis, float positionM, bool keepPositive);
    void setTrajectoriesVisible(bool visible);
    int selectedObjectId() const;
    int trackCount() const;
    int visibleSegmentCount() const;
    CameraState cameraState() const;
    void resetCamera();
    void focusCore();
    void frameSelectedTrack();
    void setCameraPreset(CameraPreset preset);
    bool openGLAvailable() const;

signals:
    void objectSelected(int objectId);
    void contextUnavailable(const QString& reason);
    void muonLayersUnavailable(const QString& reason);

protected:
    void initializeGL() override;
    void resizeGL(int width, int height) override;
    void paintGL() override;
    void mousePressEvent(QMouseEvent* event) override;
    void mouseMoveEvent(QMouseEvent* event) override;
    void mouseReleaseEvent(QMouseEvent* event) override;
    void wheelEvent(QWheelEvent* event) override;

private:
    heplab::EventData eventData_;
    QString emptyMessage_ = "Run a simulation to load a particle event.";
    int selectedObjectId_ = -1;
    bool geometryVisible_ = true;
    bool gridVisible_ = true;
    bool trajectoriesVisible_ = true;
    bool crossingsVisible_ = true;
    bool initialized_ = false;
    bool contextAvailable_ = false;
    std::unique_ptr<QOpenGLShaderProgram> shader_;
    std::unique_ptr<QOpenGLShaderProgram> trackShader_;
    std::unique_ptr<QOpenGLShaderProgram> muonSurfaceShader_;
    std::unique_ptr<QOpenGLVertexArrayObject> vao_;
    std::unique_ptr<QOpenGLBuffer> lineBuffer_;
    std::unique_ptr<QOpenGLBuffer> crossingBuffer_;
    struct MuonLayerBuffer {
        std::unique_ptr<QOpenGLBuffer> buffer;
        int vertices = 0;
        float radiusM = 0.0f;
        float opacity = 0.3f;
        bool visible = false;
    };
    std::array<MuonLayerBuffer, 3> muonLayers_;
    bool muonCutawayEnabled_ = false;
    CutawayAxis muonCutawayAxis_ = CutawayAxis::Y;
    float muonCutawayPositionM_ = 0.0f;
    bool muonCutawayKeepPositive_ = false;
    QVector3D targetM_;
    QVector3D sceneCenterM_;
    double sceneRadiusM_ = 0.265;
    float azimuthDegrees_ = 35.0f;
    float elevationDegrees_ = 25.0f;
    float distanceScale_ = 4.2f;
    QPoint pressPosition_;
    QPoint lastMousePosition_;
    Qt::MouseButton dragButton_ = Qt::NoButton;
    bool pointerMoved_ = false;
    int segmentCount_ = 0;
    int trackVertexStart_ = 0;
    int selectedTrackVertexStart_ = 0;
    int crossingCount_ = 0;

    double calculateSceneRadiusM() const;
    QVector3D calculateSceneCenterM() const;
    QVector3D cameraRight() const;
    QVector3D cameraUp() const;
    QMatrix4x4 viewProjection() const;
    void rebuildScene();
    void loadMuonLayers();
    void drawMuonLayers(const QMatrix4x4& mvp);
    int hitTest(const QPointF& pixel) const;
};
