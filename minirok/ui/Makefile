PYFILES = $(patsubst %.ui,%.py,$(wildcard *.ui))

all: $(PYFILES)

clean:
	rm -f $(PYFILES) $(patsubst %.py,%.pyc,$(PYFILES))

%.py: %.ui
	pykdeuic4 -o $@ $^
