#include <kapplication.h>
#include <kcmdlineargs.h>
#include <kmainwindow.h>
#include <kconfig.h>

class MainWindow : public KMainWindow
{
    Q_OBJECT;

    public:
      MainWindow() {}
      ~MainWindow() {}

      void saveProperties(KConfig *);
};

void MainWindow::saveProperties(KConfig *config)
{
    config->writeEntry("foo", "bar");
}

int
main (int argc, char **argv)
{
    KCmdLineArgs::init(argc, argv, "test", "test", "test", "1.0");
    KApplication app;
    MainWindow *window = new MainWindow;

    app.setTopWidget(window);
    window->show();
    return app.exec();
}

#include "saveProperties_moc.cc"
