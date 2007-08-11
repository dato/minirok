#include <qvbox.h>
#include <kapplication.h>
#include <kcmdlineargs.h>
#include <kmainwindow.h>
#include <ktoolbar.h>
#include <kxmlguiclient.h>
#include <kxmlguibuilder.h>
#include <kxmlguifactory.h>
#include <kaction.h>
#include <kactioncollection.h>

class MyVBox : public QVBox, public KXMLGUIClient
{
    Q_OBJECT;

    public:
      MyVBox(QWidget *parent);
      ~MyVBox();
      void createGUI();

    public slots:
      void noop();

    private:
      KToolBar *toolbar;
};

MyVBox::MyVBox(QWidget *parent) : QVBox(parent), KXMLGUIClient()
{
    toolbar = new KToolBar(this, "toolbar");

    KActionCollection *ac = actionCollection();
    new KAction("Action 1", 0, this, SLOT( noop() ), ac, "action1");
    new KAction("Action 2", 0, this, SLOT( noop() ), ac, "action2");
    new KAction("Action 3", 0, this, SLOT( noop() ), ac, "action3");

    setXMLFile("/tmp/xml_toolbar.rc");
    createGUI();
}

void
MyVBox::createGUI()
{
    KXMLGUIBuilder builder(this);
    KXMLGUIFactory factory(&builder, this);
    factory.addClient(this);
}

void
MyVBox::noop()
{
}

MyVBox::~MyVBox() 
{
    delete toolbar;
}

///////////////////////////////////////

class MainWindow : public KMainWindow
{
    Q_OBJECT;

    public:
      MainWindow();
      ~MainWindow();

    private:
        MyVBox *vbox;
};

MainWindow::MainWindow() : KMainWindow()
{
    vbox = new MyVBox(this);
}

MainWindow::~MainWindow()
{
    delete vbox;
}

///////////////////////////////////////

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

#include "xml_toolbar_moc.cc"
