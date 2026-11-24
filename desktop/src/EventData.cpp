#include "EventData.h"

#include <QJsonArray>
#include <QJsonValue>
#include <QSet>

#include <algorithm>
#include <cmath>

namespace heplab {
namespace {

bool finiteNumber(const QJsonValue& value, double& result)
{
    if (!value.isDouble()) {
        return false;
    }
    result = value.toDouble();
    return std::isfinite(result);
}

bool readPosition(const QJsonValue& value, Position3M& position)
{
    if (!value.isArray()) {
        return false;
    }
    const QJsonArray coordinates = value.toArray();
    if (coordinates.size() != 3) {
        return false;
    }
    return finiteNumber(coordinates.at(0), position.xM)
        && finiteNumber(coordinates.at(1), position.yM)
        && finiteNumber(coordinates.at(2), position.zM);
}

bool readMomentum(const QJsonObject& object, MomentumGeV& momentum)
{
    return finiteNumber(object.value("px"), momentum.pxGeV)
        && finiteNumber(object.value("py"), momentum.pyGeV)
        && finiteNumber(object.value("pz"), momentum.pzGeV)
        && finiteNumber(object.value("energy"), momentum.energyGeV);
}

EventData invalid(QString message)
{
    EventData result;
    result.diagnostic = std::move(message);
    return result;
}

} // namespace

int EventData::trajectorySegmentCount() const
{
    int segments = 0;
    for (const DisplayTrack& track : tracks) {
        segments += std::max(0, static_cast<int>(track.positionsM.size()) - 1);
    }
    return segments;
}

QString displayObjectKindName(DisplayObjectKind kind)
{
    switch (kind) {
    case DisplayObjectKind::GeneratedParticle:
        return "Generated particle";
    case DisplayObjectKind::ReconstructedObject:
        return "Reconstructed object";
    case DisplayObjectKind::AnalyticObject:
        return "Analytic object";
    }
    return "Unknown object";
}

EventData EventDataAdapter::fromJson(const QJsonObject& event)
{
    const QJsonObject artifact = event.value("artifact").toObject();
    const QString schema = artifact.value("schema").toString();
    if (!schema.isEmpty()
        && schema != "heplab-event-view-v1"
        && schema != "heplab-run-artifact-v1") {
        return invalid(QString("Unsupported event schema '%1'.")
                           .arg(schema));
    }

    const QJsonObject geometry = event.value("geometry").toObject();
    if (geometry.isEmpty()) {
        return invalid("Event has no detector geometry description.");
    }
    if (geometry.value("units").toString() != "metres") {
        return invalid("Detector geometry units must be declared as 'metres'.");
    }

    const QJsonValue tracksValue = event.value("tracks");
    if (!tracksValue.isArray()) {
        return invalid("Event has no 'tracks' array. Select an analytic or reconstructed event with trajectory samples.");
    }

    EventData data;
    data.eventIndex = event.value("event").toInt(-1);
    const QString runIdentity = artifact.value("run_id").toString();
    data.stableIdentity = QString("%1/event-%2")
        .arg(runIdentity.isEmpty() ? QStringLiteral("uncommitted") : runIdentity)
        .arg(data.eventIndex < 0 ? 0 : data.eventIndex);

    const QJsonValue surfacesValue = geometry.value("surfaces");
    if (!surfacesValue.isArray()) {
        return invalid("Detector geometry has no 'surfaces' array.");
    }
    const QJsonArray surfaces = surfacesValue.toArray();
    for (int index = 0; index < surfaces.size(); ++index) {
        const QJsonObject source = surfaces.at(index).toObject();
        const QString kind = source.value("kind").toString();
        DetectorSurface surface;
        surface.id = source.value("id").toString(
            QString("surface-%1").arg(index));
        if (kind == "cylinder") {
            surface.kind = DetectorSurface::Kind::Cylinder;
            if (!finiteNumber(source.value("radius_m"), surface.radiusM)
                || !finiteNumber(source.value("half_length_m"), surface.halfLengthM)
                || surface.radiusM <= 0.0 || surface.halfLengthM <= 0.0) {
                return invalid(QString("Cylinder '%1' needs positive radius_m and half_length_m values.")
                                   .arg(surface.id));
            }
        } else if (kind == "disk") {
            surface.kind = DetectorSurface::Kind::Disk;
            if (!finiteNumber(source.value("z_m"), surface.zM)
                || !finiteNumber(source.value("outer_radius_m"), surface.outerRadiusM)
                || surface.outerRadiusM <= 0.0) {
                return invalid(QString("Disk '%1' needs finite z_m and a positive outer_radius_m.")
                                   .arg(surface.id));
            }
            if (source.contains("inner_radius_m")
                && (!finiteNumber(source.value("inner_radius_m"), surface.innerRadiusM)
                    || surface.innerRadiusM < 0.0
                    || surface.innerRadiusM >= surface.outerRadiusM)) {
                return invalid(QString("Disk '%1' has an invalid inner_radius_m.")
                                   .arg(surface.id));
            }
        } else {
            return invalid(QString("Detector surface '%1' has unsupported kind '%2'.")
                               .arg(surface.id, kind));
        }
        data.detectorSurfaces.append(surface);
    }

    const QJsonArray tracks = tracksValue.toArray();
    if (tracks.isEmpty() && event.value("mode").toString() != "pythia") {
        return invalid("This event contains no renderable tracks.");
    }
    QSet<int> objectIds;
    for (int trackIndex = 0; trackIndex < tracks.size(); ++trackIndex) {
        const QJsonObject source = tracks.at(trackIndex).toObject();
        if (source.isEmpty()) {
            return invalid(QString("Track at index %1 is not an object.")
                               .arg(trackIndex));
        }
        if (!source.value("object_id").isDouble()) {
            return invalid(QString("Track at index %1 has no numeric object_id.")
                               .arg(trackIndex));
        }
        const int objectId = source.value("object_id").toInt(-1);
        if (objectId < 0 || objectIds.contains(objectId)) {
            return invalid(QString("Track object_id %1 is invalid or duplicated.")
                               .arg(objectId));
        }
        objectIds.insert(objectId);

        DisplayTrack track;
        track.objectId = objectId;
        track.stableIdentity = QString("%1/object-%2")
            .arg(data.stableIdentity).arg(objectId);
        track.pdgId = source.value("pdg_id").toInt();
        if (!finiteNumber(source.value("charge"), track.chargeE)) {
            return invalid(QString("Track %1 has no finite charge in units of e.")
                               .arg(objectId));
        }

        const QJsonObject truth = source.value("truth").toObject();
        const QJsonObject detector = source.value("detector").toObject();
        track.collection = detector.value("collection").toString();
        const QString explicitKind = source.value("object_kind").toString();
        if (explicitKind == "reconstructed" || !detector.isEmpty()) {
            track.kind = DisplayObjectKind::ReconstructedObject;
        } else if (explicitKind == "generated" || !truth.isEmpty()) {
            track.kind = DisplayObjectKind::GeneratedParticle;
        } else {
            track.kind = DisplayObjectKind::AnalyticObject;
        }

        Position3M initialPosition;
        if (!truth.isEmpty() && readPosition(truth.value("position"), initialPosition)) {
            track.initialPositionM = initialPosition;
        }
        const QJsonObject sourceMomentum = truth.value("momentum").toObject();
        if (!sourceMomentum.isEmpty()) {
            MomentumGeV momentum;
            if (!readMomentum(sourceMomentum, momentum)) {
                return invalid(QString("Track %1 truth momentum must contain finite px, py, pz, and energy values in GeV.")
                                   .arg(objectId));
            }
            track.momentum = momentum;
        }

        double reconstructedValue = 0.0;
        if (detector.contains("pt")
            && finiteNumber(detector.value("pt"), reconstructedValue)) {
            track.reconstructedPtGeV = reconstructedValue;
        }
        if (detector.contains("eta")
            && finiteNumber(detector.value("eta"), reconstructedValue)) {
            track.reconstructedEta = reconstructedValue;
        }
        if (detector.contains("phi")
            && finiteNumber(detector.value("phi"), reconstructedValue)) {
            track.reconstructedPhiRad = reconstructedValue;
        }

        const QJsonObject trajectory = source.value("trajectory").toObject();
        track.trajectoryModel = trajectory.value("model").toString(
            "backend sampled trajectory");
        const QJsonValue positionsValue = source.value("points");
        if (!positionsValue.isArray()) {
            return invalid(QString("Track %1 has no 'points' array; expected sampled [x, y, z] positions in metres.")
                               .arg(objectId));
        }
        const QJsonArray positions = positionsValue.toArray();
        for (const QJsonValue& value : positions) {
            Position3M position;
            if (!readPosition(value, position)) {
                return invalid(QString("Track %1 contains a non-finite or malformed point; expected [x_m, y_m, z_m].")
                                   .arg(objectId));
            }
            track.positionsM.append(position);
        }
        if (track.positionsM.size() < 2 && !(positions.isEmpty() && track.trajectoryModel == "none")) {
            return invalid(QString("Track %1 has fewer than two trajectory samples; at least one visible segment is required.")
                               .arg(objectId));
        }

        const QJsonValue crossingsValue = trajectory.value("crossings");
        if (crossingsValue.isArray()) {
            for (const QJsonValue& value : crossingsValue.toArray()) {
                const QJsonObject crossing = value.toObject();
                PredictedCrossing predicted;
                predicted.surfaceId = crossing.value("surface_id").toString();
                if (!readPosition(crossing.value("position_m"), predicted.positionM)) {
                    return invalid(QString("Track %1 has a malformed predicted crossing; expected position_m in metres.")
                                       .arg(objectId));
                }
                track.predictedCrossings.append(predicted);
            }
        } else if (!crossingsValue.isUndefined() && !crossingsValue.isNull()) {
            return invalid(QString("Track %1 trajectory crossings must be an array.")
                               .arg(objectId));
        }

        data.tracks.append(track);
    }

    data.valid = true;
    data.diagnostic = QString("Event %1: %2 objects, %3 sampled trajectory segments. Coordinates: metres; momenta: GeV/c.")
        .arg(data.eventIndex < 0 ? 0 : data.eventIndex)
        .arg(data.tracks.size())
        .arg(data.trajectorySegmentCount());
    return data;
}

} // namespace heplab
