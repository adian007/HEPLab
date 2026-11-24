#pragma once

#include <QJsonObject>
#include <QVector>
#include <QWidget>
#include <optional>

class ScientificPlotWidget final : public QWidget {
    Q_OBJECT

public:
    enum class Observable { InvariantMass, MuonPt, MuonEta, MissingPt, JetCount };
    enum class GraphMode { Bars, Step, NormalizedShape, Cumulative };
    struct BinRow {
        double low = 0.0;
        double high = 0.0;
        double count = 0.0;
        double uncertainty = 0.0;
        double normalized = 0.0;
        double normalizedUncertainty = 0.0;
        double cumulative = 0.0;
        double cumulativeUncertainty = 0.0;
    };
    explicit ScientificPlotWidget(QWidget* parent = nullptr);

    void setResult(const QJsonObject& result);
    void setObservable(Observable observable);
    void setGraphMode(GraphMode mode);
    GraphMode graphMode() const { return graphMode_; }
    QPair<double, double> naturalAxisRange() const;
    void setBinCount(int count);
    bool setAxisRange(double minimum, double maximum);
    void resetAxisRange();
    void setLogarithmicCounts(bool enabled);
    void setShowUncertainties(bool enabled);

    QVector<BinRow> binRows() const;
    QString title() const;
    QString units() const;
    bool isWeighted() const { return weighted_; }
    qsizetype entryCount() const { return samples().size(); }
    qsizetype eventCount() const { return eventCount_; }
    int underflowCount() const { return underflow_; }
    int overflowCount() const { return overflow_; }
    int populatedBinCount() const;
    QPair<double, double> axisBounds() const { return {minimum_, maximum_}; }

signals:
    void histogramChanged();

protected:
    void paintEvent(QPaintEvent* event) override;
    bool event(QEvent* event) override;

private:
    struct Sample {
        double value;
        qint64 event;
        double weight;
    };

    QVector<Sample> masses_;
    QVector<Sample> momenta_;
    QVector<Sample> etas_;
    QVector<Sample> missing_;
    QVector<Sample> jets_;
    bool weighted_ = false;
    GraphMode graphMode_ = GraphMode::Bars;
    const QVector<Sample>& samples() const;
    Observable observable_ = Observable::InvariantMass;
    int binCount_ = 24;
    bool logarithmicCounts_ = false;
    bool showUncertainties_ = true;
    std::optional<QPair<double, double>> axisRange_;
    QVector<double> counts_;
    QVector<double> variances_;
    QVector<double> cumulativeVariances_;
    double totalInRange_ = 0.0;
    double minimum_ = 0.0;
    double maximum_ = 1.0;
    int underflow_ = 0;
    int overflow_ = 0;
    qsizetype eventCount_ = 0;

    void rebuildHistogram();
};
