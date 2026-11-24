#pragma once

#include "EventData.h"

#include <QPointF>
#include <QWidget>

class QMouseEvent;
class QWheelEvent;

class EventProjectionWidget final : public QWidget {
    Q_OBJECT

public:
    enum class Projection { XY, XZ };
    explicit EventProjectionWidget(Projection projection, QWidget* parent = nullptr);

    void setEvent(const heplab::EventData& event);
    void clearEvent(const QString& message);
    void setSelectedObjectId(int objectId);
    void setGeometryVisible(bool visible);
    void setGridVisible(bool visible);
    void setCrossingsVisible(bool visible);
    void setTrajectoriesVisible(bool visible);
    void fitView();

    int selectedObjectId() const;
    int trackCount() const;
    int visibleSegmentCount() const;
    double sceneRadiusMetres() const;
    double zoomFactor() const;
    QPointF panOffsetMetres() const;
    QString labelForObject(int objectId) const;
    QPointF pixelForPosition(const heplab::Position3M& position) const;

    static QPointF projectPosition(const heplab::Position3M& position,
                                   Projection projection);

signals:
    void objectSelected(int objectId);

protected:
    void paintEvent(QPaintEvent* event) override;
    void mousePressEvent(QMouseEvent* event) override;
    void mouseMoveEvent(QMouseEvent* event) override;
    void mouseReleaseEvent(QMouseEvent* event) override;
    void wheelEvent(QWheelEvent* event) override;
    void resizeEvent(QResizeEvent* event) override;

private:
    Projection projection_;
    heplab::EventData eventData_;
    QString emptyMessage_ = "Run a simulation to load a particle event.";
    int selectedObjectId_ = -1;
    bool geometryVisible_ = true;
    bool gridVisible_ = true;
    bool trajectoriesVisible_ = true;
    bool crossingsVisible_ = true;
    QRect plotRect_;
    double zoomFactor_ = 1.0;
    double fitRadiusM_ = 0.1;
    QPointF panOffsetM_;
    QPoint lastMousePosition_;
    Qt::MouseButton dragButton_ = Qt::NoButton;

    QPointF toPixel(double horizontalM, double verticalM) const;
    QPointF fromPixel(const QPointF& pixel) const;
    double pixelScale() const;
    double calculateFitRadiusMetres() const;
    int hitTest(const QPointF& pixel) const;
};
