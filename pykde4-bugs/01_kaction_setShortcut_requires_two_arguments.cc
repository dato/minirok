#include <kaction.h>
#include <kshortcut.h>

int main (int argc, char *argv[])
{
    KAction *action = new KAction(NULL);
    action->setShortcut(KShortcut("Ctrl+F"));
}
