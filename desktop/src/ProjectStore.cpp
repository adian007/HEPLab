#include "ProjectStore.h"

#include <QDir>
#include <QDateTime>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QRegularExpression>
#include <QStandardPaths>
#include <QUuid>
#include <QSaveFile>

ProjectStore::ProjectStore(const QString& root)
{
    projectsRoot_ = root.isEmpty()
        ? QDir::cleanPath(QStandardPaths::writableLocation(
                              QStandardPaths::AppLocalDataLocation)
                          + "/projects")
        : QDir::cleanPath(root);
    QDir().mkpath(projectsRoot_);
    indexPath_ = projectsRoot_ + "/projects.json";
    loadIndex();
}

QString ProjectStore::root() const
{
    return projectsRoot_;
}

bool ProjectStore::loadIndex()
{
    index_ = QJsonObject{
        {"schema", "heplab-project-index-v1"},
        {"active_project", QJsonValue::Null},
        {"projects", QJsonArray{}},
    };
    QFile file(indexPath_);
    if (!file.exists()) {
        return writeIndex();
    }
    if (!file.open(QIODevice::ReadOnly)) {
        return false;
    }
    QJsonParseError error;
    const QJsonDocument document = QJsonDocument::fromJson(file.readAll(), &error);
    if (error.error != QJsonParseError::NoError || !document.isObject()) {
        return false;
    }
    const QJsonObject loaded = document.object();
    if (loaded.value("schema").toString() != "heplab-project-index-v1"
        || !loaded.value("projects").isArray()) {
        return false;
    }
    index_ = loaded;
    activeProjectId_ = loaded.value("active_project").toString();
    return true;
}

bool ProjectStore::writeIndex()
{
    QSaveFile file(indexPath_);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
        return false;
    }
    file.write(QJsonDocument(index_).toJson(QJsonDocument::Indented));
    return file.commit();
}

QString ProjectStore::createProject(const QString& name)
{
    const QString cleanName = name.trimmed();
    if (cleanName.isEmpty()) {
        return {};
    }
    const QString id = QUuid::createUuid().toString(QUuid::WithoutBraces);
    QJsonObject entry;
    entry["id"] = id;
    entry["name"] = cleanName;
    entry["directory"] = projectsRoot_ + "/" + id;
    entry["created_utc"] = QDateTime::currentDateTimeUtc().toString(Qt::ISODate);
    entry["updated_utc"] = entry["created_utc"];
    entry["last_run_id"] = QJsonValue::Null;

    QDir().mkpath(entry["directory"].toString());
    QJsonArray projects = index_.value("projects").toArray();
    projects.append(entry);
    index_["projects"] = projects;
    index_["active_project"] = id;
    activeProjectId_ = id;
    if (!writeIndex()) {
        return {};
    }

    QSaveFile manifest(entry["directory"].toString() + "/project.json");
    if (!manifest.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
        return {};
    }
    QJsonObject project;
    project["schema"] = "heplab-native-project-v1";
    project["id"] = id;
    project["name"] = cleanName;
    project["configuration"] = QJsonObject{};
    project["run_ids"] = QJsonArray{};
    project["created_utc"] = entry["created_utc"];
    project["updated_utc"] = entry["created_utc"];
    manifest.write(QJsonDocument(project).toJson(QJsonDocument::Indented));
    if (!manifest.commit()) {
        return {};
    }
    return id;
}

bool ProjectStore::openProject(const QString& projectId)
{
    const QJsonObject entry = project(projectId);
    if (entry.isEmpty()) {
        return false;
    }
    const QString directory = entry.value("directory").toString();
    if (!QDir(directory).exists()) {
        return false;
    }
    activeProjectId_ = projectId;
    index_["active_project"] = projectId;
    return writeIndex();
}

bool ProjectStore::renameProject(const QString& projectId, const QString& name)
{
    const QString cleanName = name.trimmed();
    if (cleanName.isEmpty()) {
        return false;
    }
    QJsonArray projects = index_.value("projects").toArray();
    bool found = false;
    for (int index = 0; index < projects.size(); ++index) {
        QJsonObject entry = projects.at(index).toObject();
        if (entry.value("id").toString() == projectId) {
            entry["name"] = cleanName;
            entry["updated_utc"] =
                QDateTime::currentDateTimeUtc().toString(Qt::ISODate);
            projects[index] = entry;
            found = true;
            break;
        }
    }
    if (!found) {
        return false;
    }
    index_["projects"] = projects;
    if (!writeIndex()) {
        return false;
    }

    const QString directory = project(projectId).value("directory").toString();
    QFile file(directory + "/project.json");
    if (!file.open(QIODevice::ReadWrite)) {
        return false;
    }
    QJsonParseError error;
    QJsonDocument document = QJsonDocument::fromJson(file.readAll(), &error);
    if (error.error != QJsonParseError::NoError || !document.isObject()) {
        return false;
    }
    QJsonObject manifest = document.object();
    manifest["name"] = cleanName;
    manifest["updated_utc"] =
        QDateTime::currentDateTimeUtc().toString(Qt::ISODate);
    file.resize(0);
    file.seek(0);
    file.write(QJsonDocument(manifest).toJson(QJsonDocument::Indented));
    return true;
}

bool ProjectStore::saveProject(const QString& projectId,
                               const QJsonObject& configuration,
                               const QString& runId)
{
    const QJsonObject entry = project(projectId);
    if (entry.isEmpty()) {
        return false;
    }
    const QString directory = entry.value("directory").toString();
    const QString manifestPath = directory + "/project.json";
    QJsonObject manifest;
    QFile file(manifestPath);
    if (file.exists()) {
        if (!file.open(QIODevice::ReadOnly)) {
            return false;
        }
        QJsonParseError error;
        const QJsonDocument document = QJsonDocument::fromJson(file.readAll(), &error);
        if (error.error != QJsonParseError::NoError || !document.isObject()) {
            return false;
        }
        manifest = document.object();
        file.close();
    }
    manifest["schema"] = "heplab-native-project-v1";
    manifest["id"] = projectId;
    manifest["name"] = entry.value("name");
    if (!configuration.isEmpty()) {
        manifest["configuration"] = configuration;
    }
    manifest["updated_utc"] =
        QDateTime::currentDateTimeUtc().toString(Qt::ISODate);
    QJsonArray runIds = manifest.value("run_ids").toArray();
    if (!runId.isEmpty() && !runIds.toVariantList().contains(runId)) {
        runIds.append(runId);
    }
    manifest["run_ids"] = runIds;

    QSaveFile save(manifestPath);
    if (!save.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
        return false;
    }
    save.write(QJsonDocument(manifest).toJson(QJsonDocument::Indented));
    if (!save.commit()) {
        return false;
    }

    QJsonArray projects = index_.value("projects").toArray();
    for (int index = 0; index < projects.size(); ++index) {
        QJsonObject item = projects.at(index).toObject();
        if (item.value("id").toString() == projectId) {
            item["updated_utc"] = manifest["updated_utc"];
            if (!runId.isEmpty()) {
                item["last_run_id"] = runId;
            }
            projects[index] = item;
            break;
        }
    }
    index_["projects"] = projects;
    return writeIndex();
}

QStringList ProjectStore::projectIds() const
{
    QStringList ids;
    for (const auto& value : index_.value("projects").toArray()) {
        ids.append(value.toObject().value("id").toString());
    }
    return ids;
}

QJsonObject ProjectStore::project(const QString& projectId) const
{
    for (const auto& value : index_.value("projects").toArray()) {
        const QJsonObject entry = value.toObject();
        if (entry.value("id").toString() == projectId) {
            return entry;
        }
    }
    return {};
}

QString ProjectStore::activeProjectId() const
{
    return activeProjectId_;
}

QString ProjectStore::activeProjectRoot() const
{
    return project(activeProjectId_).value("directory").toString();
}
