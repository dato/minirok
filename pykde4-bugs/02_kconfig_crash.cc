#include <kglobal.h>
#include <kmainwindow.h>
#include <kapplication.h>
#include <kcmdlineargs.h>
#include <kconfiggroup.h>

class MainWindow : public KMainWindow
{
    public:
        MainWindow() {
            KGlobal::config()->group("Foo").writeEntry("a", "b");
            KGlobal::config()->sync();
        }
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
