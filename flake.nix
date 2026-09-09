{
  description = "GUI dev environment";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };
    in {
      devShells.${system}.default = pkgs.mkShell {
        buildInputs = [ pkgs.uv ];

        LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
          pkgs.libx11
          pkgs.libxrandr
          pkgs.libxinerama
          pkgs.libxcursor
          pkgs.libxi
          pkgs.libxext
          pkgs.libGL
          pkgs.stdenv.cc.cc.lib
          pkgs.glib
        ];

        shellHook = ''
          echo "Dev shell ready. Run: uv sync && uv run python main.py"
        '';
      };
    };
}
