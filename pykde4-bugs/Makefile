EXE := $(patsubst %.cc,%,$(wildcard *.cc))
INCLUDE := -I /usr/include/KDE -I /usr/include/qt4
LIBS := -lkdeui

all: $(EXE)

clean:
	rm -f $(EXE) $(patsubst %,%_moc.cc,$(EXE))

%_moc.cc: %.cc
	moc-qt4 $^ >$@

%: %.cc %_moc.cc
	g++ -o $@ $< $(INCLUDE) $(LIBS)

%: %.cc
