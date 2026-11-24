#include "EventProjectionWidget.h"

#include <QMouseEvent>
#include <QPainter>
#include <QPainterPath>
#include <QWheelEvent>

#include <algorithm>
#include <cmath>

namespace {

double niceTickStep(double radius)
{
    const double raw = std::max(radius / 4.0, 1e-6);
    const double exponent = std::floor(std::log10(raw));
    const double scale = std::pow(10.0, exponent);
    const double fraction = raw / scale;
    const double nice = fraction <= 1.0 ? 1.0
        : fraction <= 2.0 ? 2.0
        : fraction <= 5.0 ? 5.0 : 10.0;
    return nice * scale;
}

} // namespace

EventProjectionWidget::EventProjectionWidget(Projection projection, QWidget* parent)
    : QWidget(parent), projection_(projection)
{
    setMinimumSize(215, 200);
    setMouseTracking(true);
    setFocusPolicy(Qt::StrongFocus);
    setToolTip("Wheel: zoom · right or middle drag: pan · click a trajectory: select");
}

void EventProjectionWidget::setEvent(const heplab::EventData& event)
{
    eventData_ = event;
    fitRadiusM_ = calculateFitRadiusMetres();
    selectedObjectId_ = -1;
    zoomFactor_ = 1.0;
    panOffsetM_ = {};
    emptyMessage_ = event.valid ? QString() : event.diagnostic;
    update();
}

void EventProjectionWidget::clearEvent(const QString& message)
{
    eventData_ = {};
    fitRadiusM_ = 0.1;
    selectedObjectId_ = -1;
    zoomFactor_ = 1.0;
    panOffsetM_ = {};
    emptyMessage_ = message;
    update();
}

void EventProjectionWidget::setSelectedObjectId(int objectId)
{
    if (selectedObjectId_ == objectId) {
        return;
    }
    selectedObjectId_ = objectId;
    update();
}

void EventProjectionWidget::setGeometryVisible(bool visible)
{
    if (geometryVisible_ == visible) return;
    geometryVisible_ = visible;
    update();
}

void EventProjectionWidget::setTrajectoriesVisible(bool visible)
{
    if (trajectoriesVisible_ == visible) return;
    trajectoriesVisible_ = visible;
    update();
}

void EventProjectionWidget::setCrossingsVisible(bool visible)
{
    if (crossingsVisible_ == visible) return;
    crossingsVisible_ = visible;
    update();
}

void EventProjectionWidget::setGridVisible(bool visible)
{
    if (gridVisible_ == visible) return;
    gridVisible_ = visible;
    update();
}

void EventProjectionWidget::fitView()
{
    zoomFactor_ = 1.0;
    panOffsetM_ = {};
    update();
}

int EventProjectionWidget::selectedObjectId() const
{
    return selectedObjectId_;
}

int EventProjectionWidget::trackCount() const
{
    return eventData_.valid ? static_cast<int>(std::count_if(eventData_.tracks.cbegin(),
        eventData_.tracks.cend(), [](const auto& track) { return track.positionsM.size() > 1; })) : 0;
}

int EventProjectionWidget::visibleSegmentCount() const
{
    return eventData_.valid && trajectoriesVisible_
        ? eventData_.trajectorySegmentCount() : 0;
}

double EventProjectionWidget::sceneRadiusMetres() const
{
    return fitRadiusM_;
}

double EventProjectionWidget::zoomFactor() const
{
    return zoomFactor_;
}

QPointF EventProjectionWidget::panOffsetMetres() const
{
    return panOffsetM_;
}

QString EventProjectionWidget::labelForObject(int objectId) const
{
    for (const heplab::DisplayTrack& track : eventData_.tracks) {
        if (track.objectId == objectId) {
            return QString("%1 %2 (PDG %3, q=%4 e)")
                .arg(heplab::displayObjectKindName(track.kind))
                .arg(track.objectId)
                .arg(track.pdgId)
                .arg(track.chargeE, 0, 'g', 4);
        }
    }
    return QString("Object %1").arg(objectId);
}

QPointF EventProjectionWidget::pixelForPosition(
    const heplab::Position3M& position) const
{
    const QPointF projected = projectPosition(position, projection_);
    return toPixel(projected.x(), projected.y());
}

QPointF EventProjectionWidget::projectPosition(
    const heplab::Position3M& position, Projection projection)
{
    return projection == Projection::XY
        ? QPointF(position.xM, position.yM)
        : QPointF(position.zM, position.xM);
}

double EventProjectionWidget::calculateFitRadiusMetres() const
{
    double radius = 0.0;
    const auto include = [&](double horizontal, double vertical) {
        radius = std::max(radius, std::max(std::abs(horizontal), std::abs(vertical)));
    };
    if (eventData_.valid) {
        for (const heplab::DisplayTrack& track : eventData_.tracks) {
            for (const heplab::Position3M& position : track.positionsM) {
                const QPointF projected = projectPosition(position, projection_);
                include(projected.x(), projected.y());
            }
        }
        for (const heplab::DetectorSurface& surface : eventData_.detectorSurfaces) {
            if (surface.kind == heplab::DetectorSurface::Kind::Cylinder) {
                if (projection_ == Projection::XY) {
                    include(surface.radiusM, surface.radiusM);
                } else {
                    include(surface.halfLengthM, surface.radiusM);
                }
            } else if (projection_ == Projection::XY) {
                include(surface.outerRadiusM, surface.outerRadiusM);
            } else {
                include(surface.zM, surface.outerRadiusM);
            }
        }
    }
    return std::max(radius * 1.08, 0.1);
}

double EventProjectionWidget::pixelScale() const
{
    if (plotRect_.isEmpty()) return 0.0;
    const double viewRadius = fitRadiusM_ / zoomFactor_;
    return std::min(plotRect_.width() / (2.0 * viewRadius),
                    plotRect_.height() / (2.0 * viewRadius));
}

QPointF EventProjectionWidget::toPixel(double horizontalM, double verticalM) const
{
    if (plotRect_.isEmpty()) return {};
    const double scale = pixelScale();
    return QPointF(plotRect_.center().x() + (horizontalM - panOffsetM_.x()) * scale,
                   plotRect_.center().y() - (verticalM - panOffsetM_.y()) * scale);
}

QPointF EventProjectionWidget::fromPixel(const QPointF& pixel) const
{
    const double scale = pixelScale();
    if (scale <= 0.0) return {};
    return QPointF(panOffsetM_.x() + (pixel.x() - plotRect_.center().x()) / scale,
                   panOffsetM_.y() - (pixel.y() - plotRect_.center().y()) / scale);
}

int EventProjectionWidget::hitTest(const QPointF& pixel) const
{
    if (!eventData_.valid || !trajectoriesVisible_) return -1;
    int closestObject = -1;
    double closestDistance = 13.0;
    for (const heplab::DisplayTrack& track : eventData_.tracks) {
        QPointF previous;
        bool havePrevious = false;
        for (const heplab::Position3M& point : track.positionsM) {
            const QPointF projected = projectPosition(point, projection_);
            const QPointF current = toPixel(projected.x(), projected.y());
            if (havePrevious) {
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
            havePrevious = true;
        }
    }
    return closestObject;
}

void EventProjectionWidget::resizeEvent(QResizeEvent*)
{
    plotRect_ = rect().adjusted(60, 34, -20, -54);
}

void EventProjectionWidget::mousePressEvent(QMouseEvent* event)
{
    if (event->button() == Qt::LeftButton) {
        setFocus(Qt::MouseFocusReason);
        const int objectId = hitTest(event->position());
        setSelectedObjectId(objectId);
        emit objectSelected(objectId);
        event->accept();
        return;
    }
    if (event->button() == Qt::RightButton || event->button() == Qt::MiddleButton) {
        dragButton_ = event->button();
        lastMousePosition_ = event->position().toPoint();
        event->accept();
        return;
    }
    QWidget::mousePressEvent(event);
}

void EventProjectionWidget::mouseMoveEvent(QMouseEvent* event)
{
    if (dragButton_ == Qt::NoButton) {
        QWidget::mouseMoveEvent(event);
        return;
    }
    const QPoint delta = event->position().toPoint() - lastMousePosition_;
    lastMousePosition_ = event->position().toPoint();
    const double scale = pixelScale();
    if (scale > 0.0) {
        panOffsetM_.rx() -= delta.x() / scale;
        panOffsetM_.ry() += delta.y() / scale;
        update();
    }
    event->accept();
}

void EventProjectionWidget::mouseReleaseEvent(QMouseEvent* event)
{
    if (event->button() == dragButton_) {
        dragButton_ = Qt::NoButton;
        event->accept();
        return;
    }
    QWidget::mouseReleaseEvent(event);
}

void EventProjectionWidget::wheelEvent(QWheelEvent* event)
{
    if (!eventData_.valid) {
        event->ignore();
        return;
    }
    const QPointF anchor = fromPixel(event->position());
    const double steps = event->angleDelta().y() / 120.0;
    zoomFactor_ = std::clamp(zoomFactor_ * std::pow(1.18, steps), 0.5, 24.0);
    const QPointF after = fromPixel(event->position());
    panOffsetM_ += anchor - after;
    update();
    event->accept();
}

void EventProjectionWidget::paintEvent(QPaintEvent*)
{
    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing, true);
    painter.fillRect(rect(), QColor("#101820"));
    plotRect_ = rect().adjusted(60, 34, -20, -54);
    if (plotRect_.width() < 8 || plotRect_.height() < 8) return;

    painter.setPen(QColor("#DDE6ED"));
    painter.setFont(QFont(painter.font().family(), 10, QFont::DemiBold));
    const QString title =
        projection_ == Projection::XY
            ? "XY projection · transverse plane"
            : "XZ projection · longitudinal plane";
    painter.drawText(12, 20, painter.fontMetrics().elidedText(title, Qt::ElideRight, width() - 24));

    if (!eventData_.valid) {
        painter.setPen(QColor("#F0B35A"));
        painter.drawText(plotRect_.adjusted(16, 12, -12, -12),
                         Qt::AlignCenter | Qt::TextWordWrap,
                         emptyMessage_.isEmpty()
                             ? QStringLiteral("No event loaded.") : emptyMessage_);
        painter.setPen(QColor("#536270"));
        painter.drawRect(plotRect_);
        return;
    }

    const double step = niceTickStep(200.0 / pixelScale());
    const QPointF worldTopLeft = fromPixel(plotRect_.topLeft());
    const QPointF worldBottomRight = fromPixel(plotRect_.bottomRight());
    const double left = std::min(worldTopLeft.x(), worldBottomRight.x());
    const double right = std::max(worldTopLeft.x(), worldBottomRight.x());
    const double bottom = std::min(worldTopLeft.y(), worldBottomRight.y());
    const double top = std::max(worldTopLeft.y(), worldBottomRight.y());

    painter.save();
    painter.setClipRect(plotRect_);
    painter.setPen(QPen(QColor("#23323D"), 1));
    const int firstX = static_cast<int>(std::ceil(left / step));
    const int lastX = static_cast<int>(std::floor(right / step));
    const int firstY = static_cast<int>(std::ceil(bottom / step));
    const int lastY = static_cast<int>(std::floor(top / step));
    if (gridVisible_) {
        for (int index = firstX; index <= lastX; ++index) {
            const double value = index * step;
            painter.drawLine(toPixel(value, bottom), toPixel(value, top));
        }
        for (int index = firstY; index <= lastY; ++index) {
            const double value = index * step;
            painter.drawLine(toPixel(left, value), toPixel(right, value));
        }
    }
    painter.setPen(QPen(QColor("#8A9AA7"), 1.25));
    painter.drawLine(toPixel(left, 0.0), toPixel(right, 0.0));
    painter.drawLine(toPixel(0.0, bottom), toPixel(0.0, top));

    if (geometryVisible_) {
        painter.setBrush(Qt::NoBrush);
        for (const heplab::DetectorSurface& surface : eventData_.detectorSurfaces) {
            const bool isCore = surface.kind == heplab::DetectorSurface::Kind::Cylinder
                ? (surface.radiusM <= 0.35)
                : (surface.outerRadiusM <= 0.35);
            painter.setPen(QPen(isCore ? QColor("#7CE4F8") : QColor("#447488"), isCore ? 1.4 : 0.9));
            if (surface.kind == heplab::DetectorSurface::Kind::Cylinder) {
                if (projection_ == Projection::XY) {
                    const QPointF center = toPixel(0.0, 0.0);
                    const QPointF edge = toPixel(surface.radiusM, 0.0);
                    const double radiusPx = std::abs(edge.x() - center.x());
                    painter.drawEllipse(center, radiusPx, radiusPx);
                } else {
                    const QPointF topLeft = toPixel(-surface.halfLengthM,
                                                    surface.radiusM);
                    const QPointF bottomRight = toPixel(surface.halfLengthM,
                                                         -surface.radiusM);
                    painter.drawRect(QRectF(topLeft, bottomRight).normalized());
                }
            } else if (projection_ == Projection::XY) {
                const QPointF center = toPixel(0.0, 0.0);
                const double outer = std::abs(
                    toPixel(surface.outerRadiusM, 0.0).x() - center.x());
                const double inner = std::abs(
                    toPixel(surface.innerRadiusM, 0.0).x() - center.x());
                painter.drawEllipse(center, outer, outer);
                if (inner > 0.0) painter.drawEllipse(center, inner, inner);
            } else {
                const auto drawDiskSide = [&](double sign) {
                    const QPointF outer = toPixel(surface.zM,
                                                  sign * surface.outerRadiusM);
                    const QPointF inner = toPixel(surface.zM,
                                                  sign * surface.innerRadiusM);
                    painter.drawLine(outer, inner);
                };
                drawDiskSide(-1.0);
                drawDiskSide(1.0);
            }
        }
    }

    if (trajectoriesVisible_) {
        const QColor muonNegative("#61D1FF");
        const QColor muonPositive("#FFB34D");
        const QColor otherNegative("#4D8FB3");
        const QColor otherPositive("#C28557");
        const QColor neutral("#99E694");
        const bool hasSelection = selectedObjectId_ >= 0;
        for (const heplab::DisplayTrack& track : eventData_.tracks) {
            if (track.positionsM.isEmpty()) continue;
            QPainterPath path;
            bool first = true;
            for (const heplab::Position3M& point : track.positionsM) {
                const QPointF projected = projectPosition(point, projection_);
                const QPointF pixel = toPixel(projected.x(), projected.y());
                if (first) {
                    path.moveTo(pixel);
                    first = false;
                } else {
                    path.lineTo(pixel);
                }
            }
            const bool isSelected = track.objectId == selectedObjectId_;
            const bool isMuon = std::abs(track.pdgId) == 13;
            if (isSelected) {
                painter.setPen(QPen(QColor("#FFFFFF"), 5.5,
                                    Qt::SolidLine, Qt::RoundCap, Qt::RoundJoin));
                painter.drawPath(path);
            }
            QColor trackColor = neutral;
            if (track.chargeE < 0.0) trackColor = isMuon ? muonNegative : otherNegative;
            else if (track.chargeE > 0.0) trackColor = isMuon ? muonPositive : otherPositive;
            if (hasSelection && !isSelected && !isMuon) trackColor.setAlpha(115);
            painter.setPen(QPen(trackColor,
                                isSelected ? 3.2 : (isMuon ? 2.4 : 1.7),
                                Qt::SolidLine, Qt::RoundCap, Qt::RoundJoin));
            painter.drawPath(path);
            if (!track.positionsM.isEmpty()) {
                const QPointF last = projectPosition(track.positionsM.last(), projection_);
                const QPointF endpoint = toPixel(last.x(), last.y());
                painter.setPen(QPen(QColor("#101820"), 1.0));
                painter.setBrush(trackColor);
                painter.drawEllipse(endpoint, isSelected ? 3.8 : 2.8, isSelected ? 3.8 : 2.8);
            }
            if (!crossingsVisible_) continue;
            painter.setPen(QPen(QColor("#EAF2F8"), 1.0));
            painter.setBrush(QColor("#EAF2F8"));
            for (const heplab::PredictedCrossing& crossing : track.predictedCrossings) {
                const QPointF projected = projectPosition(crossing.positionM, projection_);
                const QPointF marker = toPixel(projected.x(), projected.y());
                painter.drawRect(QRectF(marker.x() - 2.0, marker.y() - 2.0, 4.0, 4.0));
            }
        }
    }
    painter.restore();

    painter.setPen(QColor("#CBD5DD"));
    const QString horizontalLabel = projection_ == Projection::XY ? "x [m]" : "z [m]";
    const QString verticalLabel = projection_ == Projection::XY ? "y [m]" : "x [m]";
    painter.setFont(QFont(painter.font().family(), 8));
    painter.drawText(QRect(plotRect_.left(), plotRect_.bottom() + 19,
                           plotRect_.width(), 16), Qt::AlignCenter, horizontalLabel);
    painter.save();
    painter.translate(12, plotRect_.center().y());
    painter.rotate(-90.0);
    painter.drawText(QRect(-40, -8, 80, 16), Qt::AlignCenter, verticalLabel);
    painter.restore();

    painter.setPen(QColor("#91A2AF"));
    painter.setFont(QFont(painter.font().family(), 8));
    for (int index = firstX; index <= lastX; ++index) {
        const double value = index * step;
        const QPointF tick = toPixel(value, 0.0);
        painter.drawText(QRectF(tick.x() - 22, plotRect_.bottom() + 3, 44, 15),
                         Qt::AlignCenter, QString::number(value, 'g', 3));
    }
    for (int index = firstY; index <= lastY; ++index) {
        const double value = index * step;
        const QPointF tick = toPixel(0.0, value);
        painter.drawText(QRectF(22, tick.y() - 7, plotRect_.left() - 27, 14),
                         Qt::AlignRight | Qt::AlignVCenter, QString::number(value, 'g', 3));
    }
    painter.setPen(QColor("#536270"));
    painter.drawRect(plotRect_);
    painter.setPen(QColor("#AAB7C4"));
    const QString footer = tr("%1 tracks  ·  %2× zoom")
        .arg(trackCount()).arg(zoomFactor_, 0, 'f', 2);
    painter.drawText(12, height() - 7,
        painter.fontMetrics().elidedText(footer, Qt::ElideRight, width() - 24));
}
