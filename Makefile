.PHONY: help install server run client clean

PY := python3
VENV := venv
BIN  := $(VENV)/bin
PIP  := $(BIN)/pip
RUN  := $(BIN)/python

help:
	@echo "make install   Create venv + install dependencies"
	@echo "make bot       Run bot locally"
	@echo "make clean     Remove venv"

$(BIN)/activate:
	$(PY) -m venv $(VENV)

install: $(BIN)/activate
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

bot: install
	$(RUN) bot.py

clean:
	rm -rf $(VENV)