#include "DetectorViewport3D.h"

#include <QMatrix4x4>
#include <QCryptographicHash>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QtEndian>
#include <QMouseEvent>
#include <QOpenGLContext>
#include <QPainter>
#include <QSurfaceFormat>
#include <QVector2D>
#include <QVector4D>
#include <QWheelEvent>

#include <algorithm>
#include <bit>
#include <cmath>

namespace {
constexpr float kPi = 3.14159265358979323846f;
constexpr float kFieldOfViewDegrees = 40.0f;
constexpr const char* muonLayerIds[] = {"dt", "csc", "rpc"};
constexpr const char* muonLayerLabels[] = {"DT", "CSC", "RPC"};
const QVector3D muonLayerColors[] = {
    {0.22f, 0.68f, 0.54f}, {0.55f, 0.48f, 0.88f}, {0.76f, 0.42f, 0.23f}
};

QVector3D toVector(const heplab::Position3M& position)
{
    return QVector3D(static_cast<float>(position.xM),
                     static_cast<float>(position.yM),
                     static_cast<float>(position.zM));
}

QVector3D colorForTrack(const heplab::DisplayTrack& track, bool dimmed = false)
{
    const bool isMuon = std::abs(track.pdgId) == 13;
    const bool isElectron = std::abs(track.pdgId) == 11;
    QVector3D color;
    if (isMuon) {
        if (track.chargeE < 0.0) color = QVector3D(0.38f, 0.82f, 1.0f);
        else if (track.chargeE > 0.0) color = QVector3D(1.0f, 0.70f, 0.30f);
        else color = QVector3D(0.60f, 0.90f, 0.58f);
    } else if (isElectron) {
        color = track.chargeE < 0.0 ? QVector3D(0.34f, 0.86f, 0.72f)
                                    : QVector3D(0.95f, 0.52f, 0.62f);
    } else {
        if (track.chargeE < 0.0) color = QVector3D(0.30f, 0.56f, 0.70f);
        else if (track.chargeE > 0.0) color = QVector3D(0.76f, 0.52f, 0.34f);
        else color = QVector3D(0.60f, 0.90f, 0.58f);
    }
    if (dimmed) {
        color *= 0.42f;
    }
    return color;
}

} // namespace

DetectorViewport3D::DetectorViewport3D(QWidget* parent)
    : QOpenGLWidget(parent)
{
    QSurfaceFormat format;
    format.setDepthBufferSize(24);
    format.setStencilBufferSize(8);
    format.setSamples(4);
    format.setProfile(QSurfaceFormat::CoreProfile);
    format.setVersion(3, 3);
    setFormat(format);
    setMinimumSize(290, 220);
    setMouseTracking(true);
    setFocusPolicy(Qt::StrongFocus);
    setToolTip("Left drag: orbit · right or middle drag: pan · wheel: zoom · click a track: select");
}

DetectorViewport3D::~DetectorViewport3D() = default;

void DetectorViewport3D::setEvent(const heplab::EventData& event)
{
    eventData_ = event;
    emptyMessage_ = event.valid ? QString() : event.diagnostic;
    selectedObjectId_ = -1;
    sceneCenterM_ = calculateSceneCenterM();
    sceneRadiusM_ = calculateSceneRadiusM();
    targetM_ = sceneCenterM_;
    distanceScale_ = 4.2f;
    rebuildScene();
    update();
}

void DetectorViewport3D::clearEvent(const QString& message)
{
    eventData_ = {};
    emptyMessage_ = message;
    selectedObjectId_ = -1;
    targetM_ = {};
    sceneCenterM_ = {};
    sceneRadiusM_ = calculateSceneRadiusM();
    segmentCount_ = 0;
    crossingCount_ = 0;
    rebuildScene();
    update();
}

void DetectorViewport3D::setSelectedObjectId(int objectId)
{
    if (selectedObjectId_ == objectId) return;
    selectedObjectId_ = objectId;
    rebuildScene();
    update();
}

void DetectorViewport3D::setGeometryVisible(bool visible)
{
    if (geometryVisible_ == visible) return;
    geometryVisible_ = visible;
    rebuildScene();
    update();
}

void DetectorViewport3D::setMuonLayerVisible(MuonLayer layer, bool visible)
{
    muonLayers_.at(static_cast<std::size_t>(layer)).visible = visible;
    update();
}

void DetectorViewport3D::setMuonLayerOpacity(MuonLayer layer, float opacity)
{
    muonLayers_.at(static_cast<std::size_t>(layer)).opacity = std::clamp(opacity, 0.0f, 1.0f);
    update();
}

void DetectorViewport3D::setMuonCutaway(bool enabled, CutawayAxis axis, float positionM,
                                      bool keepPositive)
{
    muonCutawayEnabled_ = enabled;
    muonCutawayAxis_ = axis;
    muonCutawayPositionM_ = positionM;
    muonCutawayKeepPositive_ = keepPositive;
    update();
}

void DetectorViewport3D::loadMuonLayers()
{
    muonSurfaceShader_ = std::make_unique<QOpenGLShaderProgram>(this);
    const char* vertex = R"(
#version 330 core
layout(location = 0) in vec3 position;
uniform mat4 mvp;
out vec3 worldPosition;
void main() {
    worldPosition = position;
    gl_Position = mvp * vec4(position, 1.0);
}
)";
    const char* fragment = R"(
#version 330 core
in vec3 worldPosition;
uniform vec3 layerColor;
uniform float opacity;
uniform bool cutawayEnabled;
uniform vec4 cutawayPlane;
out vec4 fragColor;
void main() {
    vec3 normal = normalize(cross(dFdx(worldPosition), dFdy(worldPosition)));
    if (cutawayEnabled && dot(cutawayPlane, vec4(worldPosition, 1.0)) > 0.0)
        discard;
    float light = abs(dot(normal, normalize(vec3(0.4, -0.5, 0.75))));
    fragColor = vec4(layerColor * (0.45 + 0.55 * light), opacity);
}
)";
    if (!muonSurfaceShader_->addShaderFromSourceCode(QOpenGLShader::Vertex, vertex)
        || !muonSurfaceShader_->addShaderFromSourceCode(QOpenGLShader::Fragment, fragment)
        || !muonSurfaceShader_->link()) {
        emit muonLayersUnavailable(tr("CMS surface shader unavailable: %1").arg(muonSurfaceShader_->log()));
        muonSurfaceShader_.reset();
        return;
    }
    QFile manifestFile(":/cms-muon/manifest.json");
    QJsonObject manifest;
    if (manifestFile.open(QIODevice::ReadOnly))
        manifest = QJsonDocument::fromJson(manifestFile.readAll()).object();
    const auto records = manifest.value("layers").toArray();
    QStringList failed;
    for (std::size_t index = 0; index < muonLayers_.size(); ++index) {
        auto& layer = muonLayers_[index];
        layer.buffer.reset();
        layer.vertices = 0;
        layer.radiusM = 0.0f;
        const QString id = QString::fromLatin1(muonLayerIds[index]);
        QJsonObject record;
        for (const auto& value : records) {
            if (value.toObject().value("id").toString() == id) {
                record = value.toObject().value("surfaces").toObject();
                break;
            }
        }
        QFile file(":/cms-muon/" + id + "-surfaces.f32");
        QByteArray bytes;
        if (file.open(QIODevice::ReadOnly)) bytes = file.readAll();
        constexpr int vertexBytes = 3 * sizeof(float);
        const int vertexCount = record.value("vertices").toInt();
        if (manifest.value("units").toString() != "m" ||
            manifest.value("encoding").toString() != "little-endian float32 XYZ pairs" ||
            vertexCount <= 0 || vertexCount % 3 != 0 || bytes.size() / vertexBytes != vertexCount ||
            bytes.size() % vertexBytes != 0 || bytes.size() != record.value("bytes").toInt() ||
            QCryptographicHash::hash(bytes, QCryptographicHash::Sha256).toHex() !=
                record.value("sha256").toString().toLatin1()) {
            failed << id.toUpper();
            continue;
        }
        QVector<float> positions(bytes.size() / sizeof(float));
        for (qsizetype i = 0; i < positions.size(); ++i)
            positions[i] = std::bit_cast<float>(qFromLittleEndian<quint32>(bytes.constData() + i * sizeof(float)));
        if (!std::all_of(positions.cbegin(), positions.cend(), [](float value) { return std::isfinite(value); })) {
            failed << id.toUpper();
            continue;
        }
        auto buffer = std::make_unique<QOpenGLBuffer>(QOpenGLBuffer::VertexBuffer);
        if (!buffer->create() || !buffer->bind()) {
            failed << id.toUpper();
            continue;
        }
        buffer->setUsagePattern(QOpenGLBuffer::StaticDraw);
        buffer->allocate(positions.constData(), static_cast<int>(bytes.size()));
        buffer->release();
        for (qsizetype i = 0; i < positions.size(); i += 3)
            layer.radiusM = std::max(layer.radiusM, std::hypot(positions[i], positions[i+1], positions[i+2]));
        layer.vertices = vertexCount;
        layer.buffer = std::move(buffer);
    }
    if (!failed.isEmpty())
        emit muonLayersUnavailable(tr("CMS iSpy geometry could not be loaded for %1.").arg(failed.join(", ")));
}

void DetectorViewport3D::drawMuonLayers(const QMatrix4x4& mvp)
{
    if (!muonSurfaceShader_ || !muonSurfaceShader_->bind()) return;
    muonSurfaceShader_->setUniformValue("mvp", mvp);
    QVector4D plane(0.0f, 0.0f, 0.0f, -muonCutawayPositionM_);
    plane[static_cast<int>(muonCutawayAxis_)] = 1.0f;
    if (muonCutawayKeepPositive_) plane = -plane;
    muonSurfaceShader_->setUniformValue("cutawayEnabled", muonCutawayEnabled_);
    muonSurfaceShader_->setUniformValue("cutawayPlane", plane);
    glDisableVertexAttribArray(1);
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
    GLint stencilBits = 0;
    glGetIntegerv(GL_STENCIL_BITS, &stencilBits);
    const bool hasStencil = stencilBits > 0;
    if (hasStencil) {
        glStencilMask(0xff);
        glClearStencil(0);
    }
    for (std::size_t index = 0; index < muonLayers_.size(); ++index) {
        const auto& layer = muonLayers_[index];
        if (!layer.visible || layer.opacity <= 0.0f || !layer.buffer || !layer.buffer->bind()) continue;
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 0, nullptr);
        // Keep per-layer opacity predictable even where many chambers overlap.
        // Resolve the nearest surface of each subsystem, then composite the layers.
        glDepthMask(GL_TRUE);
        glClear(hasStencil ? GL_DEPTH_BUFFER_BIT | GL_STENCIL_BUFFER_BIT : GL_DEPTH_BUFFER_BIT);
        glDepthFunc(GL_LEQUAL);
        glColorMask(GL_FALSE, GL_FALSE, GL_FALSE, GL_FALSE);
        glDrawArrays(GL_TRIANGLES, 0, layer.vertices);
        glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
        glDepthMask(GL_FALSE);
        glDepthFunc(GL_EQUAL);
        if (hasStencil) {
            // Coplanar mesh faces can have identical depth. Blend each sample only once.
            glEnable(GL_STENCIL_TEST);
            glStencilFunc(GL_EQUAL, 0, 0xff);
            glStencilOp(GL_KEEP, GL_KEEP, GL_INCR);
        }
        muonSurfaceShader_->setUniformValue("layerColor", muonLayerColors[index]);
        muonSurfaceShader_->setUniformValue("opacity", layer.opacity);
        glDrawArrays(GL_TRIANGLES, 0, layer.vertices);
        if (hasStencil) glDisable(GL_STENCIL_TEST);
    }
    glDepthMask(GL_TRUE);
    glDepthFunc(GL_LEQUAL);
    glDisable(GL_BLEND);
    // Reference meshes never hide the trajectories or the event crossing markers.
    glClear(GL_DEPTH_BUFFER_BIT);
    muonSurfaceShader_->release();
}

void DetectorViewport3D::setTrajectoriesVisible(bool visible)
{
    if (trajectoriesVisible_ == visible) return;
    trajectoriesVisible_ = visible;
    rebuildScene();
    update();
}

void DetectorViewport3D::setCrossingsVisible(bool visible)
{
    if (crossingsVisible_ == visible) return;
    crossingsVisible_ = visible;
    rebuildScene();
    update();
}

void DetectorViewport3D::setGridVisible(bool visible)
{
    if (gridVisible_ == visible) return;
    gridVisible_ = visible;
    rebuildScene();
    update();
}

int DetectorViewport3D::selectedObjectId() const
{
    return selectedObjectId_;
}

int DetectorViewport3D::trackCount() const
{
    return eventData_.valid ? static_cast<int>(std::count_if(eventData_.tracks.cbegin(),
        eventData_.tracks.cend(), [](const auto& track) { return track.positionsM.size() > 1; })) : 0;
}

int DetectorViewport3D::visibleSegmentCount() const
{
    return eventData_.valid && trajectoriesVisible_ ? segmentCount_ : 0;
}

DetectorViewport3D::CameraState DetectorViewport3D::cameraState() const
{
    return {azimuthDegrees_, elevationDegrees_, distanceScale_, targetM_};
}

void DetectorViewport3D::resetCamera()
{
    setCameraPreset(CameraPreset::Isometric);
}

void DetectorViewport3D::focusCore()
{
    double coreRadius = 0.0;
    for (const auto& surface : eventData_.detectorSurfaces) {
        const double r = surface.kind == heplab::DetectorSurface::Kind::Cylinder
            ? surface.radiusM
            : surface.outerRadiusM;
        if (r > 0.0 && r <= 0.35) {
            coreRadius = std::max(coreRadius, r);
        }
    }
    if (coreRadius <= 0.0) coreRadius = 0.18;
    targetM_ = QVector3D(0.0f, 0.0f, 0.0f);
    azimuthDegrees_ = 35.0f;
    elevationDegrees_ = 25.0f;
    distanceScale_ = std::clamp(
        static_cast<float>((coreRadius * 3.8) / std::max(sceneRadiusM_, 0.05)),
        0.25f, 4.2f);
    update();
}

void DetectorViewport3D::frameSelectedTrack()
{
    if (!trajectoriesVisible_) return;
    const auto track = std::find_if(eventData_.tracks.cbegin(), eventData_.tracks.cend(),
        [this](const auto& candidate) { return candidate.objectId == selectedObjectId_; });
    if (track == eventData_.tracks.cend() || track->positionsM.size() < 2) return;

    QVector3D low = toVector(track->positionsM.first());
    QVector3D high = low;
    for (const auto& point : track->positionsM) {
        const QVector3D position = toVector(point);
        low = {std::min(low.x(), position.x()), std::min(low.y(), position.y()), std::min(low.z(), position.z())};
        high = {std::max(high.x(), position.x()), std::max(high.y(), position.y()), std::max(high.z(), position.z())};
    }
    targetM_ = (low + high) * 0.5f;
    const float aspect = width() / static_cast<float>(std::max(height(), 1));
    const float extent = (high - low).length() * 0.5f;
    distanceScale_ = std::clamp(
        static_cast<float>(4.2 * extent / (sceneRadiusM_ * std::clamp(aspect, 0.1f, 1.0f))),
        0.65f, 40.0f);
    update();
}

void DetectorViewport3D::setCameraPreset(CameraPreset preset)
{
    switch (preset) {
    case CameraPreset::Isometric:
        azimuthDegrees_ = 35.0f;
        elevationDegrees_ = 25.0f;
        break;
    case CameraPreset::XY:
        azimuthDegrees_ = -90.0f;
        elevationDegrees_ = 90.0f;
        break;
    case CameraPreset::XZ:
        azimuthDegrees_ = -90.0f;
        elevationDegrees_ = 0.0f;
        break;
    case CameraPreset::YZ:
        azimuthDegrees_ = 0.0f;
        elevationDegrees_ = 0.0f;
        break;
    }
    targetM_ = sceneCenterM_;
    distanceScale_ = 4.2f;
    update();
}

bool DetectorViewport3D::openGLAvailable() const
{
    return contextAvailable_;
}

QVector3D DetectorViewport3D::calculateSceneCenterM() const
{
    if (!eventData_.valid) return {};
    QVector3D low(0.0f, 0.0f, 0.0f);
    QVector3D high(0.0f, 0.0f, 0.0f);
    bool haveBounds = false;
    const auto include = [&](const QVector3D& value) {
        if (!haveBounds) {
            low = value;
            high = value;
            haveBounds = true;
        } else {
            low.setX(std::min(low.x(), value.x()));
            low.setY(std::min(low.y(), value.y()));
            low.setZ(std::min(low.z(), value.z()));
            high.setX(std::max(high.x(), value.x()));
            high.setY(std::max(high.y(), value.y()));
            high.setZ(std::max(high.z(), value.z()));
        }
    };
    include({0.0f, 0.0f, 0.0f});
    for (const heplab::DisplayTrack& track : eventData_.tracks) {
        for (const heplab::Position3M& point : track.positionsM) {
            include(toVector(point));
        }
    }
    for (const heplab::DetectorSurface& surface : eventData_.detectorSurfaces) {
        if (surface.kind == heplab::DetectorSurface::Kind::Cylinder) {
            include({-static_cast<float>(surface.radiusM),
                     -static_cast<float>(surface.radiusM),
                     -static_cast<float>(surface.halfLengthM)});
            include({ static_cast<float>(surface.radiusM),
                      static_cast<float>(surface.radiusM),
                      static_cast<float>(surface.halfLengthM)});
        } else {
            const float r = static_cast<float>(surface.outerRadiusM);
            const float z = static_cast<float>(surface.zM);
            include({-r, -r, z});
            include({ r,  r, z});
        }
    }
    return haveBounds ? (low + high) * 0.5f : QVector3D();
}

double DetectorViewport3D::calculateSceneRadiusM() const
{
    double radius = 0.25;
    const auto include = [&](const QVector3D& point) {
        radius = std::max(radius, static_cast<double>((point - sceneCenterM_).length()));
    };
    include({0.0f, 0.0f, 0.0f});
    for (const heplab::DisplayTrack& track : eventData_.tracks) {
        for (const heplab::Position3M& point : track.positionsM) include(toVector(point));
    }
    for (const heplab::DetectorSurface& surface : eventData_.detectorSurfaces) {
        if (surface.kind == heplab::DetectorSurface::Kind::Cylinder) {
            const double corner = std::sqrt(2.0 * surface.radiusM * surface.radiusM
                                            + surface.halfLengthM * surface.halfLengthM);
            radius = std::max(radius, sceneCenterM_.length() + corner);
        } else {
            const double extent = std::hypot(surface.outerRadiusM, surface.zM);
            radius = std::max(radius, static_cast<double>(sceneCenterM_.length())
                                      + extent);
        }
    }
    for (const auto& layer : muonLayers_) {
        if (layer.visible)
            radius = std::max(radius, static_cast<double>(layer.radiusM + sceneCenterM_.length()));
    }
    return radius * 1.06;
}

QVector3D DetectorViewport3D::cameraRight() const
{
    const float azimuth = azimuthDegrees_ * kPi / 180.0f;
    return {-std::sin(azimuth), std::cos(azimuth), 0.0f};
}

QVector3D DetectorViewport3D::cameraUp() const
{
    const float azimuth = azimuthDegrees_ * kPi / 180.0f;
    const float elevation = elevationDegrees_ * kPi / 180.0f;
    return {-std::sin(elevation) * std::cos(azimuth),
            -std::sin(elevation) * std::sin(azimuth), std::cos(elevation)};
}

QMatrix4x4 DetectorViewport3D::viewProjection() const
{
    const float radius = static_cast<float>(sceneRadiusM_);
    const float cameraDistance = radius * distanceScale_;
    const float azimuth = azimuthDegrees_ * kPi / 180.0f;
    const float elevation = elevationDegrees_ * kPi / 180.0f;
    const QVector3D camera = targetM_ + QVector3D(
        cameraDistance * std::cos(elevation) * std::cos(azimuth),
        cameraDistance * std::cos(elevation) * std::sin(azimuth),
        cameraDistance * std::sin(elevation));

    QMatrix4x4 projection;
    const float aspect = width() / static_cast<float>(std::max(height(), 1));
    const float nearPlane = std::max(radius / 2000.0f, 0.0001f);
    projection.perspective(kFieldOfViewDegrees, aspect, nearPlane,
                           cameraDistance + radius * 8.0f + (targetM_ - sceneCenterM_).length());
    QMatrix4x4 view;
    view.lookAt(camera, targetM_, cameraUp());
    return projection * view;
}

void DetectorViewport3D::initializeGL()
{
    if (!context() || !context()->isValid()) {
        contextAvailable_ = false;
        emit contextUnavailable("3D rendering needs a valid OpenGL context. Check the graphics driver.");
        return;
    }
    initializeOpenGLFunctions();
    contextAvailable_ = true;

    shader_ = std::make_unique<QOpenGLShaderProgram>(this);
    const char* vertexSource = R"(
#version 330 core
layout(location = 0) in vec3 position;
layout(location = 1) in vec3 color;
uniform mat4 mvp;
out vec3 vertexColor;
void main() {
    gl_Position = mvp * vec4(position, 1.0);
    vertexColor = color;
}
)";
    const char* fragmentSource = R"(
#version 330 core
in vec3 vertexColor;
out vec4 fragColor;
void main() {
    fragColor = vec4(vertexColor, 1.0);
}
)";
    if (!shader_->addShaderFromSourceCode(QOpenGLShader::Vertex, vertexSource)
        || !shader_->addShaderFromSourceCode(QOpenGLShader::Fragment, fragmentSource)
        || !shader_->link()) {
        contextAvailable_ = false;
        emit contextUnavailable("3D shader compilation failed: " + shader_->log());
        return;
    }

    // Core OpenGL drivers may limit native line width to one physical pixel.
    // Expand trajectories in clip space to keep width independent of distance and DPI.
    const char* trackGeometrySource = R"(
#version 330 core
layout(lines) in;
layout(triangle_strip, max_vertices=4) out;
in vec3 vertexColor[];
out vec3 trackColor;
uniform vec2 viewportPixels;
uniform float trackWidth;

void corner(vec4 point, vec2 offset) {
    trackColor = vertexColor[0];
    gl_Position = point + vec4(offset / viewportPixels * 2.0 * point.w, 0.0, 0.0);
    EmitVertex();
}

void main() {
    vec4 a = gl_in[0].gl_Position;
    vec4 b = gl_in[1].gl_Position;
    float nearA = a.z + a.w;
    float nearB = b.z + b.w;
    if (nearA < 0.0 && nearB < 0.0) return;
    if (nearA < 0.0) a = mix(a, b, nearA / (nearA - nearB));
    if (nearB < 0.0) b = mix(b, a, nearB / (nearB - nearA));
    if (a.w <= 0.0 || b.w <= 0.0) return;
    vec2 delta = (b.xy / b.w - a.xy / a.w) * viewportPixels;
    if (length(delta) < 0.0001) return;
    vec2 tangent = normalize(delta);
    vec2 perpendicular = vec2(-tangent.y, tangent.x) * trackWidth * 0.5;
    vec2 cap = tangent * trackWidth * 0.3;
    corner(a, -cap + perpendicular);
    corner(a, -cap - perpendicular);
    corner(b, cap + perpendicular);
    corner(b, cap - perpendicular);
    EndPrimitive();
}
)";
    const char* trackFragmentSource = R"(
#version 330 core
in vec3 trackColor;
out vec4 fragColor;
void main() {
    fragColor = vec4(trackColor, 1.0);
}
)";
    trackShader_ = std::make_unique<QOpenGLShaderProgram>(this);
    if (!trackShader_->addShaderFromSourceCode(QOpenGLShader::Vertex, vertexSource)
        || !trackShader_->addShaderFromSourceCode(QOpenGLShader::Geometry, trackGeometrySource)
        || !trackShader_->addShaderFromSourceCode(QOpenGLShader::Fragment, trackFragmentSource)
        || !trackShader_->link()) {
        // The standard line program remains available if wide tracks cannot be drawn.
        trackShader_.reset();
    }

    vao_ = std::make_unique<QOpenGLVertexArrayObject>(this);
    lineBuffer_ = std::make_unique<QOpenGLBuffer>(QOpenGLBuffer::VertexBuffer);
    crossingBuffer_ = std::make_unique<QOpenGLBuffer>(QOpenGLBuffer::VertexBuffer);
    if (!vao_->create() || !lineBuffer_->create() || !crossingBuffer_->create()) {
        contextAvailable_ = false;
        emit contextUnavailable("3D GPU vertex buffer allocation failed.");
        return;
    }
    initialized_ = true;
    glEnable(GL_DEPTH_TEST);
    glDepthFunc(GL_LEQUAL);
    glEnable(GL_MULTISAMPLE);
    glLineWidth(1.0f);
    loadMuonLayers();
    sceneRadiusM_ = calculateSceneRadiusM();
    rebuildScene();
}

void DetectorViewport3D::resizeGL(int width, int height)
{
    glViewport(0, 0, width, std::max(height, 1));
}

void DetectorViewport3D::rebuildScene()
{
    segmentCount_ = 0;
    crossingCount_ = 0;
    if (!initialized_ || !lineBuffer_ || !crossingBuffer_ || !vao_) return;

    const bool alreadyCurrent = QOpenGLContext::currentContext() == context();
    if (!alreadyCurrent) makeCurrent();
    if (QOpenGLContext::currentContext() != context()) return;

    QVector<float> lines;
    QVector<float> crossings;
    const float radius = static_cast<float>(sceneRadiusM_);
    const auto appendLine = [&](const QVector3D& a, const QVector3D& b,
                                const QVector3D& color) {
        lines.append(a.x()); lines.append(a.y()); lines.append(a.z());
        lines.append(color.x()); lines.append(color.y()); lines.append(color.z());
        lines.append(b.x()); lines.append(b.y()); lines.append(b.z());
        lines.append(color.x()); lines.append(color.y()); lines.append(color.z());
    };
    const auto appendCrossing = [&](const QVector3D& point) {
        const float marker = std::max(radius * 0.004f, 0.025f);
        const QVector3D color(0.94f, 0.98f, 1.0f);
        const auto appendMarkerLine = [&](const QVector3D& a, const QVector3D& b) {
            crossings.append(a.x()); crossings.append(a.y()); crossings.append(a.z());
            crossings.append(color.x()); crossings.append(color.y()); crossings.append(color.z());
            crossings.append(b.x()); crossings.append(b.y()); crossings.append(b.z());
            crossings.append(color.x()); crossings.append(color.y()); crossings.append(color.z());
        };
        appendMarkerLine(point - QVector3D(marker, 0.0f, 0.0f),
                         point + QVector3D(marker, 0.0f, 0.0f));
        appendMarkerLine(point - QVector3D(0.0f, marker, 0.0f),
                         point + QVector3D(0.0f, marker, 0.0f));
        appendMarkerLine(point - QVector3D(0.0f, 0.0f, marker),
                         point + QVector3D(0.0f, 0.0f, marker));
        ++crossingCount_;
    };

    const float axisExtent = std::max(radius + sceneCenterM_.length(), 1.0f);
    if (gridVisible_) {
        const QVector3D gridColor(0.15f, 0.21f, 0.27f);
        for (int index = -5; index <= 5; ++index) {
            const float value = index * axisExtent / 5.0f;
            appendLine({-axisExtent, value, 0.0f}, {axisExtent, value, 0.0f}, gridColor);
            appendLine({value, -axisExtent, 0.0f}, {value, axisExtent, 0.0f}, gridColor);
        }

    }
    if (geometryVisible_) {
        for (const heplab::DetectorSurface& surface : eventData_.detectorSurfaces) {
            const bool isCore = surface.kind == heplab::DetectorSurface::Kind::Cylinder
                ? (surface.radiusM <= 0.35)
                : (surface.outerRadiusM <= 0.35);
            const QVector3D surfaceColor = isCore
                ? QVector3D(0.46f, 0.88f, 0.98f)
                : QVector3D(0.20f, 0.42f, 0.48f);
            if (surface.kind == heplab::DetectorSurface::Kind::Cylinder) {
                const float r = static_cast<float>(surface.radiusM);
                const float halfLength = static_cast<float>(surface.halfLengthM);
                constexpr int divisions = 64;
                const int ribStep = isCore ? 4 : 8;
                for (int index = 0; index < divisions; ++index) {
                    const float angleA = index * 2.0f * kPi / divisions;
                    const float angleB = (index + 1) * 2.0f * kPi / divisions;
                    const QVector3D lowA(r * std::cos(angleA), r * std::sin(angleA), -halfLength);
                    const QVector3D lowB(r * std::cos(angleB), r * std::sin(angleB), -halfLength);
                    const QVector3D highA(lowA.x(), lowA.y(), halfLength);
                    const QVector3D highB(lowB.x(), lowB.y(), halfLength);
                    appendLine(lowA, lowB, surfaceColor);
                    appendLine(highA, highB, surfaceColor);
                    if (index % ribStep == 0) appendLine(lowA, highA, surfaceColor);
                }
            } else {
                const float z = static_cast<float>(surface.zM);
                const float outer = static_cast<float>(surface.outerRadiusM);
                const float inner = static_cast<float>(surface.innerRadiusM);
                constexpr int divisions = 64;
                for (int index = 0; index < divisions; ++index) {
                    const float angleA = index * 2.0f * kPi / divisions;
                    const float angleB = (index + 1) * 2.0f * kPi / divisions;
                    for (float ring : {outer, inner}) {
                        if (ring <= 0.0f) continue;
                        appendLine({ring * std::cos(angleA), ring * std::sin(angleA), z},
                                   {ring * std::cos(angleB), ring * std::sin(angleB), z},
                                   surfaceColor);
                    }
                    if (isCore && index % 16 == 0) {
                        appendLine({inner * std::cos(angleA), inner * std::sin(angleA), z},
                                   {outer * std::cos(angleA), outer * std::sin(angleA), z},
                                   surfaceColor);
                    }
                }
            }
        }
        // Subtle interaction-point marker at the origin inside the core.
        const float ip = 0.025f;
        const QVector3D ipColor(1.0f, 0.92f, 0.65f);
        appendLine({-ip, 0.0f, 0.0f}, {ip, 0.0f, 0.0f}, ipColor);
        appendLine({0.0f, -ip, 0.0f}, {0.0f, ip, 0.0f}, ipColor);
        appendLine({0.0f, 0.0f, -ip}, {0.0f, 0.0f, ip}, ipColor);
    }

    appendLine({-axisExtent, 0.0f, 0.0f}, {axisExtent, 0.0f, 0.0f},
               QVector3D(0.62f, 0.27f, 0.27f));
    appendLine({0.0f, -axisExtent, 0.0f}, {0.0f, axisExtent, 0.0f},
               QVector3D(0.29f, 0.54f, 0.33f));
    appendLine({0.0f, 0.0f, -axisExtent}, {0.0f, 0.0f, axisExtent},
               QVector3D(0.29f, 0.40f, 0.65f));

    const auto vertexCount = [&lines] { return static_cast<int>(lines.size() / 6); };
    trackVertexStart_ = vertexCount();
    const auto appendTrack = [&](const heplab::DisplayTrack& track, const QVector3D& color) {
        for (int index = 1; index < track.positionsM.size(); ++index) {
            appendLine(toVector(track.positionsM.at(index - 1)),
                       toVector(track.positionsM.at(index)), color);
            ++segmentCount_;
        }
        if (!crossingsVisible_) return;
        for (const heplab::PredictedCrossing& crossing : track.predictedCrossings) {
            appendCrossing(toVector(crossing.positionM));
        }
    };
    const heplab::DisplayTrack* selectedTrack = nullptr;
    const bool hasSelection = selectedObjectId_ >= 0;
    if (eventData_.valid && trajectoriesVisible_) {
        for (const heplab::DisplayTrack& track : eventData_.tracks) {
            if (track.objectId == selectedObjectId_) selectedTrack = &track;
            else appendTrack(track, colorForTrack(track, hasSelection && std::abs(track.pdgId) != 13));
        }
    }
    selectedTrackVertexStart_ = vertexCount();
    if (selectedTrack) appendTrack(*selectedTrack, QVector3D(1.0f, 1.0f, 1.0f));

    vao_->bind();
    lineBuffer_->bind();
    lineBuffer_->allocate(lines.constData(), lines.size() * static_cast<int>(sizeof(float)));
    lineBuffer_->release();
    crossingBuffer_->bind();
    crossingBuffer_->allocate(crossings.isEmpty() ? nullptr : crossings.constData(),
                              crossings.size() * static_cast<int>(sizeof(float)));
    crossingBuffer_->release();
    vao_->release();
    if (!alreadyCurrent) doneCurrent();
}

void DetectorViewport3D::paintGL()
{
    glClearColor(0.063f, 0.094f, 0.125f, 1.0f);
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
    if (contextAvailable_ && initialized_ && shader_ && shader_->isLinked()
        && vao_ && lineBuffer_) {
        const QMatrix4x4 mvp = viewProjection();
        vao_->bind();
        glEnableVertexAttribArray(0);
        drawMuonLayers(mvp);
        shader_->bind();
        lineBuffer_->bind();
        glEnableVertexAttribArray(0);
        glEnableVertexAttribArray(1);
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 6 * sizeof(float), nullptr);
        glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 6 * sizeof(float),
                              reinterpret_cast<void*>(3 * sizeof(float)));
        shader_->setUniformValue("mvp", mvp);
        const int totalVertices = trackVertexStart_ + segmentCount_ * 2;
        glDrawArrays(GL_LINES, 0, trackShader_ ? trackVertexStart_ : totalVertices);
        if (trackShader_ && segmentCount_ > 0) {
            const float dpr = static_cast<float>(devicePixelRatioF());
            trackShader_->bind();
            trackShader_->setUniformValue("mvp", mvp);
            trackShader_->setUniformValue("viewportPixels",
                QVector2D(width() * dpr, std::max(height(), 1) * dpr));
            trackShader_->setUniformValue("trackWidth", 2.5f * dpr);
            glDrawArrays(GL_LINES, trackVertexStart_, selectedTrackVertexStart_ - trackVertexStart_);
            trackShader_->setUniformValue("trackWidth", 4.5f * dpr);
            glDrawArrays(GL_LINES, selectedTrackVertexStart_, totalVertices - selectedTrackVertexStart_);
            shader_->bind();
        }

        if (crossingBuffer_ && crossingCount_ > 0) {
            crossingBuffer_->bind();
            glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 6 * sizeof(float), nullptr);
            glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 6 * sizeof(float),
                                  reinterpret_cast<void*>(3 * sizeof(float)));
            glDrawArrays(GL_LINES, 0, crossingCount_ * 6);
        }
        glDisableVertexAttribArray(0);
        glDisableVertexAttribArray(1);
        if (crossingBuffer_) crossingBuffer_->release();
        else lineBuffer_->release();
        vao_->release();
        shader_->release();

        QPainter painter(this);
        painter.setRenderHint(QPainter::Antialiasing, true);
        painter.setPen(QColor("#DDE6ED"));
        painter.drawText(QRect(10, 8, width() - 20, 22), Qt::AlignLeft,
                         "3D Event Inspector · coordinates [m]");
        int legendX = 10;
        const int legendY = 45;
        for (std::size_t index = 0; index < muonLayers_.size(); ++index) {
            if (!muonLayers_[index].visible || muonLayers_[index].opacity <= 0.0f ||
                !muonLayers_[index].buffer) continue;
            if (legendX == 10) {
                const QString prefix = "CMS iSpy ·";
                painter.drawText(legendX, legendY, prefix);
                legendX += painter.fontMetrics().horizontalAdvance(prefix) + 9;
            }
            const auto color = muonLayerColors[index];
            painter.setPen(QColor::fromRgbF(color.x(), color.y(), color.z()));
            const QString label = QString::fromLatin1(muonLayerLabels[index]);
            painter.drawText(legendX, legendY, label);
            legendX += painter.fontMetrics().horizontalAdvance(label) + 12;
        }
        if (muonCutawayEnabled_ && legendX > 10) {
            const QString axis = QStringLiteral("xyz").mid(static_cast<int>(muonCutawayAxis_), 1);
            const QString cutaway = tr("Cutaway · keep %1 %2 %3 m")
                .arg(axis, muonCutawayKeepPositive_ ? QStringLiteral("≥") : QStringLiteral("≤"))
                .arg(muonCutawayPositionM_, 0, 'f', 1);
            painter.setPen(QColor("#DDE6ED"));
            painter.drawText(10, legendY + painter.fontMetrics().height() + 3, cutaway);
        }
        const QVector3D origin = mvp.map(QVector3D());
        const auto drawAxisLabel = [&](const QVector3D& end, const QString& label,
                                       const QColor& color) {
            const QVector3D ndc = mvp.map(end);
            if (ndc.z() < -1.0f || ndc.z() > 1.0f) return;
            // An axis parallel to an axial camera projects to a point.
            const auto screenDistance = std::hypot((ndc.x() - origin.x()) * width() * 0.5f,
                                                   (ndc.y() - origin.y()) * height() * 0.5f);
            if (screenDistance < 12.0f) return;
            const QPointF screen((ndc.x() + 1.0f) * 0.5f * width(),
                                 (1.0f - ndc.y()) * 0.5f * height());
            const int labelWidth = painter.fontMetrics().horizontalAdvance(label);
            const int baseline = painter.fontMetrics().ascent();
            painter.setPen(color);
            painter.drawText(QPointF(
                std::clamp(screen.x() + 4.0, 4.0, std::max(4.0, double(width() - labelWidth - 4))),
                std::clamp(screen.y() - 4.0, static_cast<double>(baseline + 23),
                           std::max(double(baseline + 23), double(height() - 25)))), label);
        };
        const float labelExtent = static_cast<float>(std::max(sceneRadiusM_ * 0.9, 0.5));
        drawAxisLabel({labelExtent, 0.0f, 0.0f}, "x [m]", QColor("#F48A8A"));
        drawAxisLabel({0.0f, labelExtent, 0.0f}, "y [m]", QColor("#77D890"));
        drawAxisLabel({0.0f, 0.0f, labelExtent}, "z [m]", QColor("#83A9FF"));
        if (eventData_.valid && trajectoriesVisible_) {
            const auto screenPoint = [&](const heplab::Position3M& point) -> std::optional<QPointF> {
                const QVector4D clip = mvp * QVector4D(toVector(point), 1.0f);
                if (clip.w() <= 0.0f) return std::nullopt;
                const QVector3D ndc = clip.toVector3DAffine();
                if (std::abs(ndc.x()) > 1.0f || std::abs(ndc.y()) > 1.0f
                    || std::abs(ndc.z()) > 1.0f) return std::nullopt;
                return QPointF((ndc.x() + 1) * width() / 2, (1 - ndc.y()) * height() / 2);
            };
            const int trajectories = trackCount();
            QVector<QPointF> starts;
            QVector<QRectF> placedLabels;
            for (const auto& track : eventData_.tracks) {
                const bool isMuon = std::abs(track.pdgId) == 13;
                const bool isSelected = track.objectId == selectedObjectId_;
                if (track.positionsM.size() < 2
                    || (trajectories > 4 && !isSelected && !isMuon)) continue;
                if (const auto start = screenPoint(track.positionsM.first())) {
                    const auto overlaps = std::any_of(starts.cbegin(), starts.cend(), [&](const QPointF& other) {
                        return std::hypot(start->x() - other.x(), start->y() - other.y()) < 10;
                    });
                    if (!overlaps) {
                        starts.append(*start);
                        painter.setPen(QPen(QColor("#D7E4EC"), 1.3));
                        painter.setBrush(Qt::NoBrush);
                        painter.drawEllipse(*start, 5.0, 5.0);
                    }
                }
                const auto end = screenPoint(track.positionsM.last());
                if (!end) continue;
                const QVector3D rgb = colorForTrack(track);
                const QColor color = QColor::fromRgbF(rgb.x(), rgb.y(), rgb.z());
                painter.setPen(QPen(QColor("#101820"), 1.4));
                painter.setBrush(color);
                painter.drawEllipse(*end, isSelected ? 5.2 : 4.2, isSelected ? 5.2 : 4.2);
                if (!isMuon) continue;
                const QString name = track.pdgId == 13 ? QStringLiteral("μ−") : QStringLiteral("μ+");
                const int labelWidth = painter.fontMetrics().horizontalAdvance(name) + 12;
                const qreal x = std::clamp(end->x() + 8, 2.0, std::max(2.0, double(width() - labelWidth - 2)));
                const qreal y = std::clamp(end->y() - 25, 26.0, std::max(26.0, double(height() - 43)));
                const QRectF label(x, y, labelWidth, 20);
                const bool labelOverlaps = std::any_of(placedLabels.cbegin(), placedLabels.cend(),
                    [&](const QRectF& existing) { return existing.intersects(label); });
                if (labelOverlaps && !isSelected) continue;
                placedLabels.append(label);
                painter.setPen(Qt::NoPen);
                painter.setBrush(QColor("#101820"));
                painter.drawRoundedRect(label, 4, 4);
                painter.setPen(color);
                painter.drawText(label, Qt::AlignCenter, name);
            }
            if (trajectories > 2) {
                const QStringList legend = {
                    QStringLiteral("μ−"), QStringLiteral("μ+"),
                    QStringLiteral("Other q<0"), QStringLiteral("Other q>0")
                };
                const QList<QColor> legendColors = {
                    QColor("#61D1FF"), QColor("#FFB34D"), QColor("#4D8FB3"), QColor("#C28557")
                };
                int lx = width() - 12;
                for (int idx = legend.size() - 1; idx >= 0; --idx) {
                    const int w = painter.fontMetrics().horizontalAdvance(legend.at(idx)) + 16;
                    lx -= w;
                    if (lx < 220) break;
                    painter.setPen(Qt::NoPen);
                    painter.setBrush(legendColors.at(idx));
                    painter.drawEllipse(QPointF(lx + 4, 19), 3.5, 3.5);
                    painter.setPen(QColor("#CBD5DD"));
                    painter.drawText(lx + 11, 23, legend.at(idx));
                }
            }
        }
        painter.setPen(QColor("#AAB7C4"));
        if (eventData_.valid) {
            const QString footer = tr("Drag to orbit  ·  Right-drag to pan  ·  Scroll to zoom");
            painter.drawText(10, height() - 10,
                painter.fontMetrics().elidedText(footer, Qt::ElideRight, width() - 20));
        } else {
            painter.setPen(QColor("#F0B35A"));
            painter.drawText(rect().adjusted(24, 30, -24, -24),
                             Qt::AlignCenter | Qt::TextWordWrap,
                             emptyMessage_.isEmpty() ? QStringLiteral("No event loaded.")
                                                    : emptyMessage_);
        }
    } else {
        QPainter painter(this);
        painter.fillRect(rect(), QColor("#101820"));
        painter.setPen(QColor("#F0B35A"));
        painter.drawText(rect().adjusted(20, 20, -20, -20),
                         Qt::AlignCenter | Qt::TextWordWrap,
                         contextAvailable_ ? emptyMessage_
                             : QStringLiteral("3D unavailable: OpenGL initialization did not complete. XY and XZ views are still available."));
    }
}

int DetectorViewport3D::hitTest(const QPointF& pixel) const
{
    if (!eventData_.valid || !trajectoriesVisible_) return -1;
    const QMatrix4x4 mvp = viewProjection();
    int closestObject = -1;
    double closestDistance = 15.0;
    for (const heplab::DisplayTrack& track : eventData_.tracks) {
        QPointF previous;
        bool havePrevious = false;
        float previousDepth = 0.0f;
        for (const heplab::Position3M& point : track.positionsM) {
            const QVector3D ndc = mvp.map(toVector(point));
            const QPointF current((ndc.x() + 1.0f) * 0.5f * width(),
                                  (1.0f - ndc.y()) * 0.5f * height());
            if (havePrevious && previousDepth >= -1.0f && previousDepth <= 1.0f
                && ndc.z() >= -1.0f && ndc.z() <= 1.0f) {
                const QPointF segment = current - previous;
                const double lengthSquared = QPointF::dotProduct(segment, segment);
                const QPointF relative = pixel - previous;
                const double parameter = lengthSquared > 0.0
                    ? std::clamp(QPointF::dotProduct(relative, segment) / lengthSquared,
                                 0.0, 1.0)
                    : 0.0;
                const QPointF nearest = previous + parameter * segment;
                const double distance = std::hypot(pixel.x() - nearest.x(),
                                                   pixel.y() - nearest.y());
                if (distance < closestDistance) {
                    closestDistance = distance;
                    closestObject = track.objectId;
                }
            }
            previous = current;
            previousDepth = ndc.z();
            havePrevious = true;
        }
    }
    return closestObject;
}

void DetectorViewport3D::mousePressEvent(QMouseEvent* event)
{
    dragButton_ = event->button();
    pressPosition_ = event->position().toPoint();
    lastMousePosition_ = pressPosition_;
    pointerMoved_ = false;
    setFocus(Qt::MouseFocusReason);
    event->accept();
}

void DetectorViewport3D::mouseMoveEvent(QMouseEvent* event)
{
    const QPoint current = event->position().toPoint();
    const QPoint delta = current - lastMousePosition_;
    lastMousePosition_ = current;
    if (dragButton_ == Qt::NoButton) {
        QWidget::mouseMoveEvent(event);
        return;
    }
    if ((current - pressPosition_).manhattanLength() > 3) pointerMoved_ = true;
    if (dragButton_ == Qt::LeftButton) {
        azimuthDegrees_ += delta.x() * 0.35f;
        elevationDegrees_ = std::clamp(elevationDegrees_ + delta.y() * 0.35f,
                                       -90.0f, 90.0f);
        update();
    } else if (dragButton_ == Qt::RightButton || dragButton_ == Qt::MiddleButton) {
        const float cameraDistance = static_cast<float>(sceneRadiusM_) * distanceScale_;
        const float worldPerPixel = 2.0f * cameraDistance
            * std::tan(kFieldOfViewDegrees * kPi / 360.0f)
            / static_cast<float>(std::max(height(), 1));
        targetM_ += cameraRight() * (-delta.x() * worldPerPixel)
            + cameraUp() * (delta.y() * worldPerPixel);
        update();
    }
    event->accept();
}

void DetectorViewport3D::mouseReleaseEvent(QMouseEvent* event)
{
    if (event->button() == Qt::LeftButton && !pointerMoved_) {
        const int objectId = hitTest(event->position());
        setSelectedObjectId(objectId);
        emit objectSelected(objectId);
    }
    dragButton_ = Qt::NoButton;
    pointerMoved_ = false;
    event->accept();
}

void DetectorViewport3D::wheelEvent(QWheelEvent* event)
{
    const float steps = event->angleDelta().y() / 120.0f;
    distanceScale_ = std::clamp(distanceScale_ * std::pow(0.88f, steps),
                                0.7f, 18.0f);
    update();
    event->accept();
}
