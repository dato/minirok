#include <kapplication.h>
#include <kcmdlineargs.h>
#include <kmainwindow.h>
#include <kurlcombobox.h>
#include <kurlcompletion.h>

class MainWindow : public KMainWindow
{
    Q_OBJECT;

    public:
      MainWindow();
      ~MainWindow();

    private:
    	KURLComboBox *combo;
};

MainWindow::MainWindow() : KMainWindow()
{
      combo = new KURLComboBox(KURLComboBox::Directories, true, this, "combo");
      combo->setCompletionObject(new KURLCompletion(KURLCompletion::DirCompletion));
}

MainWindow::~MainWindow()
{
    delete combo;
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

#include "combo_moc.cc"
