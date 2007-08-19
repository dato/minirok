PYFILES = $(patsubst %.ui,%.py,$(wildcard *.ui))

all: $(PYFILES)

clean:
	rm -f $(PYFILES)

%.py: %.ui
	kdepyuic -a $^
