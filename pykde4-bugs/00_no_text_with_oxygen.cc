#include <KMainWindow>
#include <KApplication>
#include <KCmdLineArgs>
#include <KMenuBar>

class MainWindow : public KMainWindow
{
    public:
        MainWindow() { menuBar()->addMenu("&File"); }
        ~MainWindow() {}
};

int main(int argc, char *argv[])
{
    KCmdLineArgs::init(argc, argv, "test", 0, ki18n("test"), "1.0");
    KApplication app;
    MainWindow mw;
    mw.show();
    app.exec();
}
