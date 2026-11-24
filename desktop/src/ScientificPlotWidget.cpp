#include "ScientificPlotWidget.h"

#include <QHash>
#include <QHelpEvent>
#include <QJsonArray>
#include <QPainter>
#include <QToolTip>

#include <algorithm>
#include <cmath>

namespace {
QRectF plotArea(const QRect& bounds)
{
    return QRectF(bounds).adjusted(64, 42, -24, -52);
}
}

ScientificPlotWidget::ScientificPlotWidget(QWidget* parent) : QWidget(parent)
{
    setMinimumSize(260, 200);
    setAccessibleName(tr("Run distribution"));
    rebuildHistogram();
}

void ScientificPlotWidget::setResult(const QJsonObject& result)
{
    const auto analysis = result.value("analysis").toObject();
    weighted_ = analysis.value("kind").toString() == "collision";
    const auto read = [this](const QJsonArray& rows, const char* key, QVector<Sample>& values) {
        values.clear();
        values.reserve(rows.size());
        for (qsizetype index = 0; index < rows.size(); ++index) {
            const auto row = rows.at(index).toObject();
            const auto value = row.value(QLatin1String(key));
            const auto weight = row.value("weight");
            if (!value.isDouble() || !std::isfinite(value.toDouble())
                || (weighted_ && (!weight.isDouble() || !std::isfinite(weight.toDouble())))) continue;
            values.append({value.toDouble(), row.value("event").toInteger(-index - 1),
                           weighted_ ? weight.toDouble() : 1.0});
        }
    };
    const auto rows = analysis.value("event_rows").toArray();
    const auto objects = analysis.value("samples").toArray();
    read(weighted_ ? rows : analysis.value("pairs").toArray(),
        weighted_ ? "mass_gev" : "truth_mass_gev", masses_);
    read(objects, "pt_gev", momenta_);
    read(objects, "eta", etas_);
    read(rows, "met_gev", missing_);
    read(rows, "jets", jets_);
    rebuildHistogram();
}

const QVector<ScientificPlotWidget::Sample>& ScientificPlotWidget::samples() const
{
    switch (observable_) {
    case Observable::MuonPt: return momenta_;
    case Observable::MuonEta: return etas_;
    case Observable::MissingPt: return missing_;
    case Observable::JetCount: return jets_;
    default: return masses_;
    }
}

QString ScientificPlotWidget::title() const
{
    switch (observable_) {
    case Observable::MuonPt: return weighted_ ? tr("Reconstructed muon pT") : tr("Truth muon pT");
    case Observable::MuonEta: return weighted_ ? tr("Reconstructed muon pseudorapidity") : tr("Truth muon pseudorapidity");
    case Observable::MissingPt: return tr("Missing transverse momentum");
    case Observable::JetCount: return tr("Reconstructed jet multiplicity");
    default: return weighted_ ? tr("Reconstructed dimuon mass before the mass window")
                              : tr("Truth-pair invariant mass");
    }
}

QString ScientificPlotWidget::units() const
{
    switch (observable_) {
    case Observable::MuonPt: return tr("pT [GeV/c]");
    case Observable::MuonEta: return tr("Pseudorapidity (eta)");
    case Observable::MissingPt: return tr("Missing pT [GeV/c]");
    case Observable::JetCount: return tr("Jets per event");
    default: return tr("Mass [GeV/c²]");
    }
}

QPair<double, double> ScientificPlotWidget::naturalAxisRange() const
{
    if (observable_ == Observable::MuonEta) return {-6.0, 6.0};
    double maximum = 1.0;
    for (const auto& sample : samples()) maximum = std::max(maximum, sample.value);
    return {0.0, maximum * 1.05};
}

void ScientificPlotWidget::setObservable(Observable observable)
{
    if (observable_ == observable) return;
    observable_ = observable;
    resetAxisRange();
}

void ScientificPlotWidget::setGraphMode(GraphMode mode)
{
    if (graphMode_ == mode) return;
    graphMode_ = mode;
    emit histogramChanged();
    update();
}

void ScientificPlotWidget::setBinCount(int count)
{
    binCount_ = std::clamp(count, 2, 200);
    rebuildHistogram();
}

bool ScientificPlotWidget::setAxisRange(double minimum, double maximum)
{
    if (!(maximum > minimum) || !std::isfinite(maximum - minimum)) return false;
    axisRange_ = qMakePair(minimum, maximum);
    rebuildHistogram();
    return true;
}

void ScientificPlotWidget::resetAxisRange()
{
    axisRange_.reset();
    rebuildHistogram();
}

void ScientificPlotWidget::setLogarithmicCounts(bool enabled)
{
    logarithmicCounts_ = enabled;
    update();
}

void ScientificPlotWidget::setShowUncertainties(bool enabled)
{
    showUncertainties_ = enabled;
    update();
}

void ScientificPlotWidget::rebuildHistogram()
{
    const auto& values = samples();
    const auto range = axisRange_.value_or(naturalAxisRange());
    minimum_ = range.first;
    maximum_ = range.second;
    counts_.fill(0.0, binCount_);
    variances_.fill(0.0, binCount_);
    cumulativeVariances_.fill(0.0, binCount_);
    totalInRange_ = 0.0;
    underflow_ = overflow_ = 0;
    QHash<qint64, QHash<int, double>> eventCounts;
    for (const auto& sample : values) {
        if (sample.value < minimum_) {
            ++underflow_;
        } else if (sample.value > maximum_) {
            ++overflow_;
        } else {
            const int bin = std::min(binCount_ - 1, static_cast<int>(
                (sample.value - minimum_) / (maximum_ - minimum_) * binCount_));
            counts_[bin] += sample.weight;
            totalInRange_ += sample.weight;
            eventCounts[sample.event][bin] += sample.weight;
        }
    }
    for (const auto& event : eventCounts) {
        for (auto bin = event.cbegin(); bin != event.cend(); ++bin)
            variances_[bin.key()] += bin.value() * bin.value();
        double prefix = 0.0;
        for (int i = 0; i < binCount_; ++i) {
            prefix += event.value(i, 0.0);
            cumulativeVariances_[i] += prefix * prefix;
        }
    }
    eventCount_ = eventCounts.size();
    setAccessibleDescription(tr("%1 samples, %2 bins, %3 underflow and %4 overflow.")
        .arg(values.size()).arg(binCount_).arg(underflow_).arg(overflow_));
    emit histogramChanged();
    update();
}

int ScientificPlotWidget::populatedBinCount() const
{
    int populated = 0;
    for (int i = 0; i < binCount_; ++i) {
        if (counts_.at(i) != 0.0 || variances_.at(i) > 0.0) ++populated;
    }
    return populated;
}

QVector<ScientificPlotWidget::BinRow> ScientificPlotWidget::binRows() const
{
    QVector<BinRow> rows;
    rows.reserve(binCount_);
    const double step = (maximum_ - minimum_) / binCount_;
    const bool canNorm = totalInRange_ > 0.0;
    double running = 0.0;
    for (int i = 0; i < binCount_; ++i) {
        const double c = counts_.at(i);
        const double u = std::sqrt(variances_.at(i));
        running += c;
        rows.append({
            minimum_ + i * step,
            minimum_ + (i + 1) * step,
            c,
            u,
            canNorm ? c / totalInRange_ : 0.0,
            canNorm ? u / totalInRange_ : 0.0,
            running,
            std::sqrt(cumulativeVariances_.at(i)),
        });
    }
    return rows;
}

bool ScientificPlotWidget::event(QEvent* event)
{
    if (event->type() != QEvent::ToolTip) return QWidget::event(event);
    const auto* help = static_cast<QHelpEvent*>(event);
    const auto plot = plotArea(rect());
    if (eventCount_ == 0 || !plot.contains(help->pos())) {
        QToolTip::hideText();
        return true;
    }
    const int bin = std::clamp(static_cast<int>((help->pos().x() - plot.left())
        / plot.width() * binCount_), 0, binCount_ - 1);
    const double step = (maximum_ - minimum_) / binCount_;
    const double count = counts_[bin];
    const double uncertainty = std::sqrt(variances_[bin]);
    QString tip = tr("%1 to %2 · %3\n%4: %5\nEvent-level uncertainty: ±%6")
        .arg(minimum_ + bin * step, 0, 'g', 5).arg(minimum_ + (bin + 1) * step, 0, 'g', 5)
        .arg(units(), weighted_ ? tr("Sum of weights") : tr("Entries"))
        .arg(count, 0, 'g', 6).arg(uncertainty, 0, 'g', 4);
    if (graphMode_ == GraphMode::NormalizedShape && totalInRange_ > 0.0) {
        tip += tr("\nNormalized fraction: %1 ± %2")
            .arg(count / totalInRange_, 0, 'g', 4)
            .arg(uncertainty / totalInRange_, 0, 'g', 3);
    } else if (graphMode_ == GraphMode::Cumulative) {
        double cum = 0.0;
        for (int i = 0; i <= bin; ++i) cum += counts_[i];
        tip += tr("\nCumulative: %1 ± %2")
            .arg(cum, 0, 'g', 6)
            .arg(std::sqrt(cumulativeVariances_[bin]), 0, 'g', 4);
    }
    QToolTip::showText(help->globalPos(), tip, this);
    return true;
}

void ScientificPlotWidget::paintEvent(QPaintEvent*)
{
    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing);
    const auto colors = palette();
    painter.fillRect(rect(), colors.base());
    const auto plot = plotArea(rect());
    if (plot.width() <= 0 || plot.height() <= 0) return;

    const QColor ink = colors.text().color();
    painter.setPen(ink);
    QFont titleFont = font();
    titleFont.setBold(true);
    painter.setFont(titleFont);
    painter.drawText(QRectF(14, 6, width() - 28, 27), Qt::AlignVCenter,
        painter.fontMetrics().elidedText(title(), Qt::ElideRight, width() - 28));
    painter.setFont(font());
    if (samples().isEmpty()) {
        painter.drawText(plot, Qt::AlignCenter | Qt::TextWordWrap,
            tr("The current run has no entries for this observable."));
        return;
    }
    if (graphMode_ == GraphMode::NormalizedShape && totalInRange_ <= 0.0) {
        painter.drawText(plot, Qt::AlignCenter | Qt::TextWordWrap,
            tr("Unit-area normalization is unavailable because the in-range sum of weights is non-positive (%1).")
                .arg(totalInRange_, 0, 'g', 4));
        return;
    }

    QVector<double> plotCounts(binCount_, 0.0);
    QVector<double> plotErrors(binCount_, 0.0);
    if (graphMode_ == GraphMode::NormalizedShape) {
        for (int i = 0; i < binCount_; ++i) {
            plotCounts[i] = counts_[i] / totalInRange_;
            plotErrors[i] = std::sqrt(variances_[i]) / totalInRange_;
        }
    } else if (graphMode_ == GraphMode::Cumulative) {
        double running = 0.0;
        for (int i = 0; i < binCount_; ++i) {
            running += counts_[i];
            plotCounts[i] = running;
            plotErrors[i] = std::sqrt(cumulativeVariances_[i]);
        }
    } else {
        for (int i = 0; i < binCount_; ++i) {
            plotCounts[i] = counts_[i];
            plotErrors[i] = std::sqrt(variances_[i]);
        }
    }

    const bool log = logarithmicCounts_ && !weighted_ && graphMode_ != GraphMode::NormalizedShape;
    double bottom = log ? 0.5 : 0.0;
    double top = graphMode_ == GraphMode::NormalizedShape ? 0.01 : (weighted_ ? 0.01 : 2.0);
    for (int i = 0; i < binCount_; ++i) {
        const double error = showUncertainties_ ? plotErrors[i] : 0.0;
        top = std::max(top, plotCounts[i] + error);
        if (weighted_) bottom = std::min(bottom, plotCounts[i] - error);
    }
    top *= 1.08;
    if (weighted_) bottom *= 1.08;
    const auto scale = [&](double value) { return log ? std::log10(std::max(value, bottom)) : value; };
    const auto y = [&](double value) {
        const double fraction = (scale(value) - scale(bottom)) / (scale(top) - scale(bottom));
        return plot.bottom() - plot.height() * fraction;
    };
    const auto tick = [](double value) { return QString::number(value, 'g', 4); };
    QColor grid = ink;
    grid.setAlpha(42);
    for (int line = 0; line <= 4; ++line) {
        const double fraction = line / 4.0;
        const double value = log ? std::pow(10.0, scale(bottom) + fraction * (scale(top) - scale(bottom)))
                                 : bottom + (top - bottom) * fraction;
        const double position = y(value);
        painter.setPen(grid);
        painter.drawLine(QPointF(plot.left(), position), QPointF(plot.right(), position));
        painter.setPen(ink);
        painter.drawText(QRectF(0, position - 9, plot.left() - 6, 18),
                         Qt::AlignRight | Qt::AlignVCenter, tick(value));
    }

    const QColor accent = colors.highlight().color();
    const double binWidth = plot.width() / binCount_;
    painter.save();
    painter.setClipRect(plot);
    painter.setPen(grid);
    painter.drawLine(QPointF(plot.left(), y(0)), QPointF(plot.right(), y(0)));
    const bool stepLine = graphMode_ == GraphMode::Step
        || graphMode_ == GraphMode::NormalizedShape
        || graphMode_ == GraphMode::Cumulative;
    for (int i = 0; i < binCount_; ++i) {
        const double count = plotCounts[i];
        const double position = y(count);
        const double left = plot.left() + i * binWidth;
        if (graphMode_ == GraphMode::Bars && count != 0) {
            const double zero = y(0);
            painter.fillRect(QRectF(left, std::min(zero, position),
                std::max(1.0, binWidth - 1.0), std::abs(zero - position)), accent);
        } else if (stepLine) {
            if (graphMode_ == GraphMode::NormalizedShape && count > 0.0) {
                QColor fill = accent;
                fill.setAlpha(55);
                const double zero = y(0);
                painter.fillRect(QRectF(left, std::min(zero, position),
                    binWidth, std::abs(zero - position)), fill);
            }
            painter.setPen(QPen(accent, 2));
            painter.drawLine(QPointF(left, position), QPointF(left + binWidth, position));
            if (i > 0) painter.drawLine(QPointF(left, y(plotCounts[i - 1])), QPointF(left, position));
        }
        if (!showUncertainties_ || plotErrors[i] == 0.0) continue;
        const double error = plotErrors[i];
        const double high = y(count + error);
        const double low = y(count - error);
        const double center = left + binWidth / 2;
        const double cap = std::min(4.0, binWidth / 2);
        painter.setPen(ink);
        painter.drawLine(QPointF(center, high), QPointF(center, low));
        painter.drawLine(QPointF(center - cap, high), QPointF(center + cap, high));
        painter.drawLine(QPointF(center - cap, low), QPointF(center + cap, low));
    }
    painter.restore();

    const int populated = populatedBinCount();
    if (eventCount_ == 1 || populated == 1) {
        const QString badge = eventCount_ == 1
            ? tr("Descriptive view · 1 in-range event")
            : tr("Low-statistics · 1 populated bin");
        const int bw = painter.fontMetrics().horizontalAdvance(badge) + 14;
        const QRectF badgeRect(plot.right() - bw - 6, plot.top() + 6, bw, 20);
        painter.save();
        painter.setPen(QPen(colors.mid().color(), 1));
        painter.setBrush(colors.alternateBase());
        painter.drawRoundedRect(badgeRect, 4, 4);
        painter.setPen(ink);
        painter.drawText(badgeRect, Qt::AlignCenter, badge);
        painter.restore();
    }

    painter.setPen(ink);
    painter.drawLine(plot.bottomLeft(), plot.bottomRight());
    const int divisions = plot.width() < 320 ? 2 : 4;
    for (int index = 0; index <= divisions; ++index) {
        const double fraction = index / static_cast<double>(divisions);
        const double x = plot.left() + fraction * plot.width();
        painter.drawText(QRectF(x - 28, plot.bottom() + 2, 56, 16), Qt::AlignCenter,
            tick(minimum_ + fraction * (maximum_ - minimum_)));
    }
    painter.drawText(QRectF(plot.left(), plot.bottom() + 18, plot.width(), 16), Qt::AlignCenter, units());
    QString yLabel;
    if (graphMode_ == GraphMode::NormalizedShape) yLabel = tr("Unit-area fraction");
    else if (graphMode_ == GraphMode::Cumulative) yLabel = weighted_ ? tr("Cumulative Σw") : tr("Cumulative entries");
    else yLabel = weighted_ ? tr("Sum of weights") : log ? tr("Entries (log)") : tr("Entries");
    painter.save();
    painter.translate(12, plot.center().y());
    painter.rotate(-90);
    painter.drawText(QRectF(-plot.height() / 2, -10, plot.height(), 20), Qt::AlignCenter, yLabel);
    painter.restore();
    QString footer = tr("%1 entries (%2 events) · %3 below · %4 above")
        .arg(samples().size()).arg(eventCount_).arg(underflow_).arg(overflow_);
    if (weighted_) footer += tr(" · raw signed weights (no lumi scaling)");
    if (logarithmicCounts_ && (weighted_ || graphMode_ == GraphMode::NormalizedShape))
        footer += tr(" · log Y disabled for signed/normalized");
    if (showUncertainties_) footer += tr(" · √Σw²");
    painter.drawText(QRect(14, height() - 18, width() - 28, 17), Qt::AlignVCenter,
        painter.fontMetrics().elidedText(footer, Qt::ElideRight, width() - 28));
}
