#include "WorkerClient.h"

#include <QJsonDocument>
#include <QCoreApplication>
#include <QStandardPaths>
#include <QDir>
#include <QFileInfo>

WorkerClient::WorkerClient(QObject* parent)
    : QObject(parent)
{
    connect(&process_, &QProcess::readyReadStandardOutput, this, &WorkerClient::readOutput);
    connect(&process_, &QProcess::readyReadStandardError, this, [this]() {
        const QString error = QString::fromUtf8(process_.readAllStandardError()).trimmed();
        if (!error.isEmpty()) {
            emit workerError(error);
        }
    });
    connect(&process_,
            qOverload<int, QProcess::ExitStatus>(&QProcess::finished),
            this,
            &WorkerClient::processFinished);
}

void WorkerClient::start(const QString& repositoryRoot, const QString& projectRoot)
{
    if (process_.state() != QProcess::NotRunning) {
        return;
    }

    const QString absoluteProjectRoot = QDir(projectRoot).absolutePath();
    if (!QDir().mkpath(absoluteProjectRoot)) {
        emit workerError("Could not create the HEPLab project directory");
        return;
    }
    const QStringList workerOptions{"--project-root", absoluteProjectRoot};
#ifdef Q_OS_WIN
    const QDir appDir(QCoreApplication::applicationDirPath());
    const QDir workerDir(appDir.filePath("worker"));
    if (workerDir.exists()) {
        const QString bundledWorker = workerDir.filePath("heplab-worker.exe");
        if (!QFileInfo(bundledWorker).isFile()) {
            emit workerError("The packaged HEPLab worker is missing");
            return;
        }
        process_.setWorkingDirectory(workerDir.absolutePath());
        process_.start(bundledWorker, workerOptions);
        return;
    }
#endif

    const QString root = repositoryRoot.trimmed();
    if (root.isEmpty()) {
        emit workerError("HEPLab repository root could not be determined");
        return;
    }

    const QStringList workerArguments = QStringList{"-m", "heplab.desktop.worker"} + workerOptions;
    process_.setWorkingDirectory(root);
#ifdef Q_OS_WIN
    const QString localPython = QDir(root).filePath(".venv/Scripts/python.exe");
#else
    const QString localPython = QDir(root).filePath(".venv/bin/python");
#endif
    if (QFileInfo::exists(localPython)) {
        process_.start(localPython, workerArguments);
        return;
    }

    QString uv = qEnvironmentVariable("HEPLAB_UV");
    if (uv.isEmpty()) {
        uv = QStandardPaths::findExecutable("uv");
    }
    if (uv.isEmpty()) {
        emit workerError("uv executable is unavailable; set HEPLAB_UV");
        return;
    }

    QStringList arguments;
    arguments << "run"
              << "--project" << QDir::toNativeSeparators(repositoryRoot)
              << "--locked" << "--extra" << "serve" << "python";
    arguments += workerArguments;
    process_.start(uv, arguments);
}

void WorkerClient::restart(const QString& repositoryRoot, const QString& projectRoot)
{
    stop();
    pendingOutput_.clear();
    nextRequestId_ = 1;
    start(repositoryRoot, projectRoot);
}

void WorkerClient::stop()
{
    if (process_.state() != QProcess::NotRunning) {
        process_.closeWriteChannel();
        if (!process_.waitForFinished(3000)) {
            process_.kill();
        }
    }
}

bool WorkerClient::isRunning() const
{
    return process_.state() == QProcess::Running;
}

int WorkerClient::sendRequest(const QString& operation, const QJsonObject& arguments)
{
    if (process_.state() != QProcess::Running) {
        emit workerError("local worker is not running");
        return -1;
    }

    const int requestId = nextRequestId_++;
    QJsonObject message;
    message["id"] = requestId;
    message["op"] = operation;
    message["args"] = arguments;
    const QByteArray line = QJsonDocument(message).toJson(QJsonDocument::Compact) + "\n";
    process_.write(line);
    return requestId;
}

void WorkerClient::readOutput()
{
    pendingOutput_.append(process_.readAllStandardOutput());
    while (true) {
        const int newline = pendingOutput_.indexOf('\n');
        if (newline < 0) {
            break;
        }
        const QByteArray line = pendingOutput_.left(newline).trimmed();
        pendingOutput_.remove(0, newline + 1);
        if (line.isEmpty()) {
            continue;
        }

        QJsonParseError error;
        const QJsonDocument document = QJsonDocument::fromJson(line, &error);
        if (error.error != QJsonParseError::NoError || !document.isObject()) {
            emit workerError("worker returned malformed JSON: " + error.errorString());
            continue;
        }
        const QJsonObject object = document.object();
        if (object.contains("protocol")) {
            emit handshakeReceived(object);
        } else if (object.contains("id")) {
            emit responseReceived(object["id"].toInt(), object);
        }
    }
}

void WorkerClient::processFinished(int exitCode, QProcess::ExitStatus exitStatus)
{
    if (exitStatus == QProcess::CrashExit || exitCode != 0) {
        emit workerError(QString("local worker exited unexpectedly (code %1)").arg(exitCode));
    }
}
