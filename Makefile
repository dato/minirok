all: ui minirok.1

ui:
	$(MAKE) -C $(CURDIR)/minirok/ui

clean:
	rm -f minirok.1
	rm -rf coverage .coverage
	$(MAKE) -C $(CURDIR)/minirok/ui clean

minirok.1: minirok.xml
	docbook2x-man $<

test:
	nosetests -a '!large' minirok

alltest:
	nosetests minirok

coverage:
	rm -rf coverage .coverage
	nosetests --with-coverage --cover-package=minirok \
	  --cover-html --cover-html-dir=$(CURDIR)/coverage minirok

.PHONY: all ui clean test coverage
