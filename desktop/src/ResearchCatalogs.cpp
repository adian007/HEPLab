#include "ResearchCatalogs.h"

#include <QApplication>
#include <QByteArray>
#include <QCoreApplication>
#include <QDesktopServices>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QFrame>
#include <QJsonDocument>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QLocale>
#include <QSettings>
#include <QSize>
#include <QSizePolicy>
#include <QSplitter>
#include <QTabWidget>
#include <QTextBrowser>
#include <QTextDocument>
#include <QUrl>
#include <QVBoxLayout>

namespace heplab {
namespace {

QJsonObject readJson(const QString& path)
{
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) return {};
    return QJsonDocument::fromJson(file.readAll()).object();
}

QString displayValue(const QJsonValue& value)
{
    if (value.isDouble()) return QString::number(value.toInteger());
    return value.toString(QStringLiteral("Unavailable")).toHtmlEscaped();
}

QString link(const QUrl& url, const QString& label)
{
    return QStringLiteral("<a href=\"%1\">%2</a>")
        .arg(QString::fromLatin1(url.toEncoded()).toHtmlEscaped(), label.toHtmlEscaped());
}

QString evidenceId(const QJsonObject& module, const QJsonObject& step)
{
    return module.value("id").toString() + '/' + step.value("id").toString();
}

QString notebookGallery()
{
    QDir directory(qEnvironmentVariable("HEPLAB_REPOSITORY_ROOT",
                                         QCoreApplication::applicationDirPath()));
    do {
        if (QFileInfo::exists(directory.filePath("notebooks/gallery/gallery.json")))
            return directory.absoluteFilePath("notebooks/gallery");
    } while (directory.cdUp());
    return {};
}

QString documentStyleSheet(const QPalette&)
{
    const auto pal = QApplication::palette();
    const bool dark = pal.color(QPalette::Base).lightness() < 128;
    const QString text = dark ? QStringLiteral("#e4edf5") : QStringLiteral("#152635");
    const QString muted = dark ? QStringLiteral("#9fb1c2") : QStringLiteral("#4c6073");
    const QString border = dark ? QStringLiteral("#39424e") : QStringLiteral("#c5d1dc");
    const QString accent = dark ? QStringLiteral("#83d2ee") : QStringLiteral("#185f83");
    return QStringLiteral(
        "body { color: %1; font-size: 10pt; }"
        "h2 { margin: 0 0 8px 0; font-size: 14pt; color: %1; }"
        "h3 { margin: 16px 0 8px 0; font-size: 11pt; color: %1; }"
        "h4 { margin: 12px 0 4px 0; font-size: 10.5pt; color: %1; }"
        "p, li { line-height: 150%; margin: 4px 0 8px 0; color: %1; }"
        "table.kv { width: 100%; border-collapse: collapse; margin: 8px 0 12px 0; }"
        "table.kv td, table.kv th { padding: 6px 10px; border-bottom: 1px solid %3; text-align: left; vertical-align: top; color: %1; }"
        "table.kv th { color: %4; font-weight: 600; width: 32%; }"
        "table.card { width: 100%; border-collapse: collapse; margin: 10px 0; border-left: 3px solid %4; }"
        "table.card td { padding: 8px 12px; color: %1; }"
        "span.badge { color: %4; font-size: 9pt; font-weight: 600; }"
        "span.badge-muted { color: %2; font-size: 9pt; font-weight: 600; }")
        .arg(text, muted, border, accent);
}

QString keyValueRow(const QString& label, const QString& valueHtml)
{
    return QStringLiteral("<tr><th>%1</th><td>%2</td></tr>")
        .arg(label.toHtmlEscaped(), valueHtml);
}

} // namespace

OpenDataWorkspace::OpenDataWorkspace(QWidget* parent)
    : QWidget(parent), datasets_(new QListWidget(this)), status_(new QLabel(this))
{
    datasets_->setObjectName("cmsDatasets");
    auto* layout = new QVBoxLayout(this);
    layout->setContentsMargins(0, 0, 0, 0);
    status_->setWordWrap(true);
    status_->setText(tr("Waiting for the local worker to provide the recorded CMS dataset catalog."));
    layout->addWidget(status_);

    auto* search = new QLineEdit(this);
    search->setPlaceholderText(tr("Filter by dataset name, format, era, record or DOI"));
    search->setAccessibleName(tr("Search CMS dataset catalog"));
    search->setClearButtonEnabled(true);
    layout->addWidget(search);
    auto* split = new QSplitter(this);
    datasets_->setAccessibleName(tr("CMS dataset manifests"));
    auto* tabs = new QTabWidget(split);
    const QStringList names{tr("Metadata"), tr("Certification"), tr("Provenance"),
                            tr("Files"), tr("Analysis scope")};
    for (std::size_t index = 0; index < sections_.size(); ++index) {
        auto* browser = new QTextBrowser(tabs);
        browser->setAccessibleName(names.at(index));
        browser->document()->setDocumentMargin(18);
        browser->document()->setDefaultStyleSheet("p { line-height: 145%; } h2 { margin-bottom: 12px; }");
        browser->setOpenLinks(false);
        connect(browser, &QTextBrowser::anchorClicked, this, [](const QUrl& url) {
            if (url.isValid() && url.scheme() == "https") QDesktopServices::openUrl(url);
        });
        tabs->addTab(browser, names.at(index));
        sections_[index] = browser;
    }
    split->addWidget(datasets_);
    split->addWidget(tabs);
    split->setStretchFactor(1, 2);
    split->restoreState(QSettings().value("workspace/cmsCatalogSplit").toByteArray());
    connect(split, &QSplitter::splitterMoved, this, [split] {
        QSettings().setValue("workspace/cmsCatalogSplit", split->saveState());
    });
    layout->addWidget(split, 1);
    showManifest(-1);

    connect(datasets_, &QListWidget::currentRowChanged, this, &OpenDataWorkspace::showManifest);
    connect(search, &QLineEdit::textChanged, this, [this](const QString& query) {
        QListWidgetItem* firstMatch = nullptr;
        for (int index = 0; index < datasets_->count(); ++index) {
            auto* item = datasets_->item(index);
            const bool matches = item->data(Qt::UserRole + 1).toString()
                .contains(query.trimmed(), Qt::CaseInsensitive);
            item->setHidden(!matches);
            if (matches && !firstMatch) firstMatch = item;
        }
        auto* item = datasets_->currentItem();
        if (!item || item->isHidden()) datasets_->setCurrentItem(firstMatch);
        if (!firstMatch && datasets_->count()) {
            for (auto* section : sections_)
                section->setPlainText(tr("No datasets match the current filter."));
        }
    });
}

void OpenDataWorkspace::setManifests(const QJsonArray& manifests)
{
    datasets_->clear();
    for (const auto& value : manifests) {
        const auto manifest = value.toObject();
        if (!manifest.value("name").isString()) continue;
        const auto label = QStringLiteral("%1\n%2   ·   %3")
            .arg(manifest.value("name").toString(), manifest.value("format").toString(),
                 manifest.value("era").toString());
        auto* item = new QListWidgetItem(label, datasets_);
        item->setData(Qt::UserRole, manifest);
        item->setData(Qt::UserRole + 1,
                      label + ' ' + QString::number(manifest.value("record").toInteger())
                            + ' ' + manifest.value("doi").toString());
    }
    status_->setText(datasets_->count() == 0
        ? tr("The worker returned no supported CMS dataset manifests.")
        : tr("%n recorded CMS dataset manifest(s). Review certification before physics use.",
             nullptr, datasets_->count()));
    if (datasets_->count()) datasets_->setCurrentRow(0);
}

void OpenDataWorkspace::setCatalogError(const QString& error)
{
    datasets_->clear();
    status_->setText(tr("Catalog unavailable. %1").arg(error));
}

void OpenDataWorkspace::showManifest(int row)
{
    if (row < 0) {
        for (auto* section : sections_)
            section->setPlainText(tr("Select a dataset to inspect its manifest."));
        return;
    }
    const auto manifest = datasets_->item(row)->data(Qt::UserRole).toJsonObject();
    const auto terms = manifest.value("terms").toObject();
    const auto certification = manifest.value("certification").toObject();
    const auto files = manifest.value("files").toArray();
    const QString css = documentStyleSheet(palette());
    for (auto* section : sections_) {
        section->document()->setDefaultStyleSheet(css);
    }

    QString html = QStringLiteral(
        "<h2>%1</h2>"
        "<p><span class='badge'>Recorded experimental data</span></p>"
        "<table class='card'><tr><td>%2</td></tr></table>"
        "<table class='kv'>")
        .arg(displayValue(manifest.value("name")), displayValue(manifest.value("note")));
    html += keyValueRow(tr("Experiment"), displayValue(manifest.value("experiment")));
    html += keyValueRow(tr("Era"), displayValue(manifest.value("era")));
    html += keyValueRow(tr("Format"), displayValue(manifest.value("format")));
    html += keyValueRow(tr("Files in manifest"), QString::number(files.size()));
    html += QStringLiteral("</table>");
    sections_[0]->setHtml(html);

    html = QStringLiteral("<h2>%1</h2><table class='kv'>").arg(tr("Run certification").toHtmlEscaped());
    html += keyValueRow(tr("Scope"), displayValue(certification.value("scope")));
    html += keyValueRow(tr("SHA-256"), QStringLiteral("<code>%1</code>").arg(displayValue(certification.value("sha256"))));
    html += keyValueRow(tr("Manifest path"), QStringLiteral("<code>%1</code>").arg(displayValue(certification.value("path"))));
    html += QStringLiteral("</table><p>%1</p>").arg(
        tr("Apply validated run certification before physics analysis. Certification metadata describes recorded luminosity masks, not detector calibration.").toHtmlEscaped());
    sections_[1]->setHtml(html);

    html = QStringLiteral("<h2>%1</h2><table class='kv'>").arg(tr("Provenance & terms").toHtmlEscaped());
    html += keyValueRow(tr("Record"), displayValue(manifest.value("record")));
    html += keyValueRow(tr("DOI"), displayValue(manifest.value("doi")));
    html += keyValueRow(tr("License"), displayValue(terms.value("license")));
    html += keyValueRow(tr("Attribution"), displayValue(terms.value("attribution")));
    html += QStringLiteral("</table>");
    const QUrl portal(manifest.value("portal_url").toString());
    if (portal.isValid() && portal.scheme() == "https")
        html += QStringLiteral("<p>%1</p>").arg(link(portal, tr("Open CERN Open Data record")));
    sections_[2]->setHtml(html);

    html = QStringLiteral("<h2>%1</h2><p>%2</p><table class='kv'><tr><th>%3</th><th>%4</th><th>%5</th></tr>")
        .arg(tr("Files in manifest (%1)").arg(files.size()).toHtmlEscaped(),
             tr("Sizes and checksums come directly from the dataset manifest.").toHtmlEscaped(),
             tr("Filename").toHtmlEscaped(),
             tr("Size").toHtmlEscaped(),
             tr("Adler-32").toHtmlEscaped());
    for (const auto& fileValue : files) {
        const auto file = fileValue.toObject();
        html += QStringLiteral("<tr><td><code>%1</code></td><td>%2</td><td><code>%3</code></td></tr>")
            .arg(displayValue(file.value("filename")),
                 QLocale().formattedDataSize(file.value("size_bytes").toInteger()).toHtmlEscaped(),
                 file.contains("adler32") ? displayValue(file.value("adler32")) : QStringLiteral("—"));
    }
    sections_[3]->setHtml(html + QStringLiteral("</table>"));

    sections_[4]->setHtml(QStringLiteral(
        "<h2>%1</h2>"
        "<table class='card'><tr><td>"
        "<p><b>%2</b></p>"
        "<p style='margin-bottom:0'>%3</p>"
        "</td></tr></table>"
        "<p>%4</p>")
        .arg(tr("Analysis scope & limitations").toHtmlEscaped(),
             tr("Recorded CMS Open Data is distinct from generated simulation.").toHtmlEscaped(),
             tr("This workspace provides the recorded dataset's manifest and certification references. "
                "Apply its validated run certification before analysing the data in a supported HEPLab workflow.").toHtmlEscaped(),
             tr("Simulation plots in Runs / Comparisons use committed simulation artifacts and are not luminosity-normalized.").toHtmlEscaped()));
}

LearningWorkspace::LearningWorkspace(QWidget* parent)
    : QWidget(parent), lessons_(new QListWidget(this)), details_(new QTextBrowser(this))
{
    lessons_->setObjectName("learningLessons");
    const auto curriculum = readJson(":/training/curriculum.json");
    if (curriculum.value("schema").toString() == "heplab-training-catalog-v1")
        modules_ = curriculum.value("modules").toArray();
    progressKey_ = QStringLiteral("training/revision-%1/evidence")
        .arg(curriculum.value("revision").toInt());
    completed_ = QSettings().value(progressKey_).toStringList();
    notebookDirectory_ = notebookGallery();
    if (!notebookDirectory_.isEmpty())
        notebooks_ = readJson(QDir(notebookDirectory_).filePath("gallery.json"))
            .value("entries").toArray();

    auto* layout = new QVBoxLayout(this);
    layout->setContentsMargins(0, 0, 0, 0);
    auto* split = new QSplitter(this);
    lessons_->setAccessibleName(tr("HEPLab lessons"));
    details_->setAccessibleName(tr("Lesson instructions and evidence"));
    details_->setOpenLinks(false);
    lessons_->setUniformItemSizes(true);
    lessons_->setAlternatingRowColors(true);
    lessons_->setTextElideMode(Qt::ElideRight);
    lessons_->setMinimumWidth(220);
    lessons_->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Expanding);
    details_->setMinimumWidth(260);
    details_->setFrameShape(QFrame::StyledPanel);
    details_->setFrameShadow(QFrame::Plain);
    split->addWidget(lessons_);
    split->addWidget(details_);
    split->setHandleWidth(1);
    split->setCollapsible(0, false);
    split->setCollapsible(1, false);
    split->setStretchFactor(1, 2);
    const QByteArray savedSplit = QSettings().value("workspace/trainingSplit").toByteArray();
    if (savedSplit.isEmpty())
        split->setSizes({280, 520});
    else
        split->restoreState(savedSplit);
    connect(split, &QSplitter::splitterMoved, this, [split] {
        QSettings().setValue("workspace/trainingSplit", split->saveState());
    });
    layout->addWidget(split, 1);
    connect(lessons_, &QListWidget::currentRowChanged, this, &LearningWorkspace::showLesson);
    connect(details_, &QTextBrowser::anchorClicked, this, [this](const QUrl& url) {
        if (url.isLocalFile() && QFileInfo(url.toLocalFile()).absolutePath() == notebookDirectory_
            && QFileInfo(url.toLocalFile()).suffix() == "ipynb")
            QDesktopServices::openUrl(url);
    });
    refreshLessons();
}

void LearningWorkspace::recordProjectOpened()
{
    recordEvidence("project_state", QJsonObject{{"opened", true}});
}

void LearningWorkspace::recordEventViewed(const QJsonObject& event)
{
    if (event.value("tracks").toArray().isEmpty()) return;
    const auto artifact = event.value("artifact").toObject();
    recordEvidence("event_view", QJsonObject{{"schema", artifact.value("schema")}});
}

void LearningWorkspace::recordEvidence(const QString& kind, const QJsonObject& facts)
{
    bool changed = false;
    for (const auto& moduleValue : modules_) {
        const auto module = moduleValue.toObject();
        for (const auto& stepValue : module.value("steps").toArray()) {
            const auto step = stepValue.toObject();
            const auto evidence = step.value("completion_evidence").toObject();
            const auto required = evidence.value("required").toObject();
            if (evidence.value("kind").toString() != kind || required.isEmpty()) continue;
            bool matches = true;
            for (auto it = required.constBegin(); it != required.constEnd(); ++it)
                matches = matches && facts.value(it.key()) == it.value();
            const auto id = evidenceId(module, step);
            if (matches && !completed_.contains(id)) {
                completed_.append(id);
                changed = true;
            }
        }
    }
    if (changed) {
        QSettings().setValue(progressKey_, completed_);
        refreshLessons();
    }
}

void LearningWorkspace::refreshLessons()
{
    const int previous = lessons_->currentRow();
    lessons_->clear();
    for (const auto& value : modules_) {
        const auto module = value.toObject();
        const auto steps = module.value("steps").toArray();
        int verified = 0;
        for (const auto& step : steps)
            if (completed_.contains(evidenceId(module, step.toObject()))) ++verified;
        auto* item = new QListWidgetItem(
            tr("%1\n%2 of %3 exercises verified")
                .arg(module.value("title").toString())
                .arg(verified)
                .arg(steps.size()));
        item->setSizeHint(QSize(0, 52));
        item->setToolTip(module.value("title").toString());
        lessons_->addItem(item);
    }
    if (lessons_->count()) lessons_->setCurrentRow(qMax(previous, 0));
    else details_->setPlainText(tr("The bundled HEPLab curriculum is unavailable."));
}

void LearningWorkspace::showLesson(int row)
{
    if (row < 0) return;
    const auto module = modules_.at(row).toObject();
    QString html = QStringLiteral(
        "<h2>%1</h2>"
        "<p><span class='badge-muted'>%2</span></p>"
        "<table class='card'><tr><td><h3 style='margin-top:0'>%3</h3><ul>")
        .arg(displayValue(module.value("title")),
             tr("%n minutes", nullptr, module.value("duration_minutes").toInt()).toHtmlEscaped(),
             tr("Learning objectives").toHtmlEscaped());
    for (const auto& goal : module.value("learning_objectives").toArray())
        html += QStringLiteral("<li>%1</li>").arg(displayValue(goal));
    html += QStringLiteral("</ul></td></tr></table><h3>%1</h3>").arg(tr("Practical exercises").toHtmlEscaped());
    for (const auto& stepValue : module.value("steps").toArray()) {
        const auto step = stepValue.toObject();
        const auto evidence = step.value("completion_evidence").toObject();
        const auto kind = evidence.value("kind").toString();
        QString instruction;
        if (kind == "project_state")
            instruction = tr("Open Home / Projects. Choose an existing project and click Open, or create a project.");
        else if (kind == "event_view")
            instruction = tr("Run an analytic simulation and open the Event Inspector. Orbit the event in 3D, select a track, and inspect its position, momentum and predicted detector crossings.");
        else
            instruction = tr("Complete this activity using the documented workflow. This desktop build cannot verify its required evidence.");
        const bool verified = completed_.contains(evidenceId(module, step));
        const auto status = verified
            ? tr("Evidence recorded")
            : (kind == "project_state" || kind == "event_view")
                ? tr("Awaiting Workbench evidence") : tr("External evidence required");
        html += QStringLiteral(
            "<table class='card'><tr><td>"
            "<h4 style='margin:0 0 6px 0'>%1</h4>"
            "<p><span class='%2'>%3</span> &nbsp; <span class='badge-muted'>%4</span></p>"
            "<p>%5</p>")
            .arg(displayValue(step.value("title")),
                 verified ? QStringLiteral("badge") : QStringLiteral("badge-muted"),
                 status.toHtmlEscaped(),
                 displayValue(evidence.value("contract")),
                 instruction.toHtmlEscaped());
        const auto required = evidence.value("required").toObject();
        if (status == tr("External evidence required") && !required.isEmpty()) {
            html += QStringLiteral("<table class='kv'>");
            for (auto it = required.constBegin(); it != required.constEnd(); ++it) {
                const QString value = it.value().isBool()
                    ? (it.value().toBool() ? tr("Yes") : tr("No")) : displayValue(it.value());
                html += keyValueRow(it.key(), value);
            }
            html += QStringLiteral("</table>");
        }
        html += QStringLiteral("</td></tr></table>");
    }
    for (const auto& entryValue : notebooks_) {
        const auto entry = entryValue.toObject();
        if (entry.value("module") != module.value("id")) continue;
        const QString name = entry.value("path").toString();
        if (name.isEmpty() || QFileInfo(name).fileName() != name) continue;
        const QString path = QDir(notebookDirectory_).filePath(name);
        if (!QFileInfo::exists(path)) continue;
        html += QStringLiteral("<table class='card'><tr><td><h3 style='margin-top:0'>%1</h3><p style='margin-bottom:0'>%2 · %3</p></td></tr></table>")
            .arg(tr("Notebook").toHtmlEscaped(), link(QUrl::fromLocalFile(path), name),
                 displayValue(entry.value("scope")));
    }
    details_->document()->setDocumentMargin(18);
    details_->document()->setDefaultStyleSheet(documentStyleSheet(palette()));
    details_->setHtml(html);
}

} // namespace heplab
