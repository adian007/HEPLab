#pragma once

#include <QJsonObject>
#include <QString>
#include <QStringList>

class ProjectStore final {
public:
    explicit ProjectStore(const QString& root = {});

    QString root() const;
    QString createProject(const QString& name);
    bool openProject(const QString& projectId);
    bool renameProject(const QString& projectId, const QString& name);
    bool saveProject(const QString& projectId,
                     const QJsonObject& configuration,
                     const QString& runId = {});

    QStringList projectIds() const;
    QJsonObject project(const QString& projectId) const;
    QString activeProjectId() const;
    QString activeProjectRoot() const;

private:
    QString indexPath_;
    QString projectsRoot_;
    QJsonObject index_;
    QString activeProjectId_;

    bool loadIndex();
    bool writeIndex();
};
