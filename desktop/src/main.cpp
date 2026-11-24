#include "MainWindow.h"

#include <QApplication>
#include <QIcon>

int main(int argc, char* argv[])
{
    QApplication app(argc, argv);
    QApplication::setApplicationName("HEPLab Workbench");
    QApplication::setOrganizationName("HEPLab");
    QApplication::setApplicationVersion("0.1.0");
    app.setWindowIcon(QIcon(QStringLiteral(":/branding/heplab-logo.png")));

    heplab::MainWindow window;
    window.show();
    return app.exec();
}
