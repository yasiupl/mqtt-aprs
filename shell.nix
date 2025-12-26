{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = [
    pkgs.python3
    pkgs.python3Packages.paho-mqtt
    pkgs.python3Packages.setproctitle
    pkgs.python3Packages.aprslib
  ];
}
