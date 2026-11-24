#pragma once

#include <QJsonObject>
#include <QObject>
#include <QProcess>

class WorkerClient final : public QObject {
    Q_OBJECT

public:
    explicit WorkerClient(QObject* parent = nullptr);

    void start(const QString& repositoryRoot, const QString& projectRoot);
    void restart(const QString& repositoryRoot, const QString& projectRoot);
    void stop();
    int sendRequest(const QString& operation, const QJsonObject& arguments = {});

    bool isRunning() const;

signals:
    void handshakeReceived(const QJsonObject& handshake);
    void responseReceived(int requestId, const QJsonObject& response);
    void workerError(const QString& message);

private slots:
    void readOutput();
    void processFinished(int exitCode, QProcess::ExitStatus exitStatus);

private:
    QProcess process_;
    QByteArray pendingOutput_;
    int nextRequestId_ = 1;
};
