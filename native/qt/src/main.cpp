#include <QApplication>

#include "mainwindow.hpp"

int main(int argc, char* argv[]) {
    QApplication application(argc, argv);
    QApplication::setApplicationName("PowerDeck");
    QApplication::setOrganizationName("PowerDeck");

    MainWindow window;
    window.show();
    return application.exec();
}
