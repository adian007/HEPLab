#pragma once

#include <QJsonArray>
#include <QJsonObject>
#include <QStringList>
#include <QWidget>
#include <array>

class QLabel;
class QListWidget;
class QTextBrowser;

namespace heplab {

class OpenDataWorkspace final : public QWidget {
public:
    explicit OpenDataWorkspace(QWidget* parent = nullptr);
    void setManifests(const QJsonArray& manifests);
    void setCatalogError(const QString& error);

private:
    void showManifest(int row);

    QListWidget* datasets_;
    std::array<QTextBrowser*, 5> sections_{};
    QLabel* status_;
};

class LearningWorkspace final : public QWidget {
public:
    explicit LearningWorkspace(QWidget* parent = nullptr);
    void recordProjectOpened();
    void recordEventViewed(const QJsonObject& event);

private:
    void recordEvidence(const QString& kind, const QJsonObject& facts);
    void refreshLessons();
    void showLesson(int row);

    QListWidget* lessons_;
    QTextBrowser* details_;
    QJsonArray modules_;
    QJsonArray notebooks_;
    QString notebookDirectory_;
    QString progressKey_;
    QStringList completed_;
};

} // namespace heplab
