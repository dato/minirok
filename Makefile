all: ui minirok.1

ui:
	$(MAKE) -C $(CURDIR)/minirok/ui

clean:
	rm -f minirok.1
	$(MAKE) -C $(CURDIR)/minirok/ui clean

minirok.1: minirok.xml
	docbook2x-man $<
