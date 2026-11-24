#pragma once

#include <QJsonObject>
#include <QString>
#include <QVector>

#include <optional>

namespace heplab {

struct Position3M {
    double xM = 0.0;
    double yM = 0.0;
    double zM = 0.0;
};

struct MomentumGeV {
    double pxGeV = 0.0;
    double pyGeV = 0.0;
    double pzGeV = 0.0;
    double energyGeV = 0.0;
};

enum class DisplayObjectKind {
    GeneratedParticle,
    ReconstructedObject,
    AnalyticObject,
};

struct PredictedCrossing {
    QString surfaceId;
    Position3M positionM;
};

struct DisplayTrack {
    int objectId = -1;
    QString stableIdentity;
    DisplayObjectKind kind = DisplayObjectKind::AnalyticObject;
    int pdgId = 0;
    double chargeE = 0.0;
    QVector<Position3M> positionsM;
    QVector<PredictedCrossing> predictedCrossings;
    QString trajectoryModel;
    QString collection;
    std::optional<Position3M> initialPositionM;
    std::optional<MomentumGeV> momentum;
    std::optional<double> reconstructedPtGeV;
    std::optional<double> reconstructedEta;
    std::optional<double> reconstructedPhiRad;
};

struct DetectorSurface {
    enum class Kind { Cylinder, Disk };

    QString id;
    Kind kind = Kind::Cylinder;
    double radiusM = 0.0;
    double halfLengthM = 0.0;
    double zM = 0.0;
    double innerRadiusM = 0.0;
    double outerRadiusM = 0.0;
};

struct EventData {
    bool valid = false;
    QString diagnostic;
    QString stableIdentity;
    int eventIndex = -1;
    QVector<DisplayTrack> tracks;
    QVector<DetectorSurface> detectorSurfaces;

    int trajectorySegmentCount() const;
};

class EventDataAdapter final {
public:
    // Backend trajectory samples and detector surface geometry are both in metres.
    static EventData fromJson(const QJsonObject& event);
};

QString displayObjectKindName(DisplayObjectKind kind);

} // namespace heplab
