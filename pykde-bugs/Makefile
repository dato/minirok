EXE := $(patsubst %.cc,%,$(wildcard *.cc))
INCLUDE := -I/usr/include/kde -I/usr/include/qt3
LIBS := -lqt-mt -lkdecore -lkdeui -lkio

all: $(EXE)

clean:
	rm -f $(EXE) $(patsubst %,%_moc.cc,$(EXE))

%_moc.cc: %.cc
	moc $^ >$@

%: %.cc %_moc.cc
	g++ -o $@ $< $(INCLUDE) $(LIBS)

%: %.cc
