#pragma once

#include <QApplication>
#include <QFont>
#include <QPalette>
#include <QStyle>
#include <QStyleFactory>

inline void applyWorkbenchTheme(bool dark, bool compact)
{
    auto* app = qobject_cast<QApplication*>(QCoreApplication::instance());
    app->setStyleSheet({});
    app->setStyle(QStyleFactory::create("Fusion"));
    QFont uiFont = app->font();
#ifdef Q_OS_WIN
    uiFont.setFamily(QStringLiteral("Segoe UI"));
#endif
    uiFont.setPointSizeF(compact ? 9.0 : 10.0);
    app->setFont(uiFont);
    QPalette palette = app->style()->standardPalette();
    if (dark) {
        palette.setColor(QPalette::Window, QColor("#191d24"));
        palette.setColor(QPalette::Base, QColor("#11151b"));
        palette.setColor(QPalette::AlternateBase, QColor("#202630"));
        palette.setColor(QPalette::Button, QColor("#2a323e"));
        for (auto role : {QPalette::WindowText, QPalette::Text, QPalette::ButtonText})
            palette.setColor(role, QColor("#e4edf5"));
        palette.setColor(QPalette::Disabled, QPalette::ButtonText, QColor("#8193a3"));
        palette.setColor(QPalette::Disabled, QPalette::Text, QColor("#8193a3"));
        palette.setColor(QPalette::Highlight, QColor("#24678a"));
        palette.setColor(QPalette::HighlightedText, Qt::white);
    } else {
        palette.setColor(QPalette::Window, QColor("#eaf0f5"));
        palette.setColor(QPalette::Base, QColor("#ffffff"));
        palette.setColor(QPalette::AlternateBase, QColor("#f1f5f8"));
        palette.setColor(QPalette::Button, QColor("#dce8f1"));
        for (auto role : {QPalette::WindowText, QPalette::Text, QPalette::ButtonText})
            palette.setColor(role, QColor("#152635"));
        palette.setColor(QPalette::Disabled, QPalette::ButtonText, QColor("#627486"));
        palette.setColor(QPalette::Disabled, QPalette::Text, QColor("#627486"));
        palette.setColor(QPalette::Highlight, QColor("#185f83"));
        palette.setColor(QPalette::HighlightedText, Qt::white);
    }
    palette.setColor(QPalette::PlaceholderText, dark ? QColor("#9baabd") : QColor("#54677a"));
    app->setPalette(palette);
    const QString edge = dark ? "#39424e" : "#a5b4c1";
    const QString accent = dark ? "#83d2ee" : "#185f83";
    const QString rail = dark ? "#11151b" : "#dde6ed";
    const QString hover = dark ? "#283442" : "#d1e2ed";
    app->setStyleSheet(QString(R"(
        QToolBar { border: 0; border-bottom: 1px solid %1; spacing: 6px; padding: 5px 10px; }
        QToolBar#inspectorControls { padding: 3px 6px; spacing: 5px; }
        QToolButton, QPushButton, QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit { min-height: %3px; }
        QPushButton { padding: 0 9px; background: palette(button); border: 1px solid %1; border-radius: 4px; }
        QPushButton:hover:enabled { background: %5; }
        QPushButton[primary="true"]:enabled { color: white; background: #245f7e; border-color: #4d93ae; font-weight: 600; }
        QPushButton:focus, QToolButton:focus, QLineEdit:focus { border: 1px solid %2; }
        QToolBar#inspectorControls QPushButton, QToolBar#inspectorControls QComboBox,
        QToolBar#inspectorControls QToolButton { min-height: 23px; }
        QLabel#eventSummary { color: %2; padding: 3px 8px; font-weight: 600; }
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
            background: palette(base); color: palette(text); padding-left: 6px;
        }
        QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {
            background: palette(alternate-base); color: palette(disabled, text);
        }
        QTextEdit#eventProperties { border: 1px solid %1; background: palette(base); }
        QTabBar::tab { padding: 6px 9px; }
        QTabBar::tab:selected { color: %2; font-weight: 600; }
        QWidget#inspectorWorkspace > QSplitter::handle { background: %1; }
        QDockWidget::title { background: palette(alternate-base); padding: 6px 8px; text-align: left; font-weight: 600; }
        QLabel[workspaceTitle="true"] { font-size: 23px; font-weight: 600; padding-bottom: 4px; }
        QWidget#workspaceRail { background: %4; border-right: 1px solid %1; }
        QLabel#workspaceBrand { font-size: 22px; font-weight: 700; color: %2; padding: 4px 4px 12px; }
        QListWidget#mainNavigation { background: transparent; border: 0; }
        QListWidget#mainNavigation::item { padding: 7px 5px; border: 1px solid transparent; border-radius: 4px; }
        QListWidget#mainNavigation::item:hover:!selected { background: %5; }
        QListWidget#mainNavigation::item:selected { background: palette(highlight); color: palette(highlighted-text); }
        QListWidget#mainNavigation::item:focus { border-color: %2; }
        QListWidget#learningLessons { border: 0; border-right: 1px solid %1; padding: 6px 4px; }
        QListWidget#learningLessons::item { min-height: 52px; padding: 8px 10px; border: 1px solid transparent; border-radius: 4px; }
        QListWidget#learningLessons::item:hover:!selected { background: %5; }
        QListWidget#learningLessons::item:selected { background: palette(highlight); color: palette(highlighted-text); }
        QListWidget#learningLessons::item:focus { border-color: %2; }
        QHeaderView::section { background: palette(button); color: palette(button-text); border: 0; border-bottom: 1px solid %1; padding: 5px; }
        QGroupBox { border: 1px solid %1; margin-top: 12px; padding-top: 9px; }
        QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
    )").arg(edge, accent).arg(compact ? 21 : 27).arg(rail, hover));
}
