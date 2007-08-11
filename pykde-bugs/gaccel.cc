#include <iostream>

#include <kapplication.h>
#include <kcmdlineargs.h>
#include <kmainwindow.h>
#include <kglobalaccel.h>
#include <kshortcut.h>

class MainWindow : public KMainWindow
{
    Q_OBJECT;

    public:
      MainWindow();
      ~MainWindow();

    private:
    	KGlobalAccel *gaccel;

    public slots:
    	void slot_action();
};

MainWindow::MainWindow() : KMainWindow()
{
      gaccel = new KGlobalAccel(this);
      gaccel->insert("action", "Action", "", KShortcut("Ctrl+Alt+u"), 0, this, SLOT(slot_action()));
      gaccel->updateConnections();
}

MainWindow::~MainWindow()
{
    delete gaccel;
}

void
MainWindow::slot_action()
{
      std::cout << "Inside slot_action()" << std::endl;
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

#include "gaccel_moc.cc"
