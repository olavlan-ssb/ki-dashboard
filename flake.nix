{
  description = "Dev env for marimo-dashboard";

  inputs = {
    flake-parts.url = "github:hercules-ci/flake-parts";
    nixpkgs.url = "https://channels.nixos.org/nixpkgs-unstable/nixexprs.tar.zst";
  };

  outputs = inputs @ {flake-parts, ...}:
    flake-parts.lib.mkFlake {inherit inputs;} {
      systems = ["x86_64-linux" "aarch64-linux" "aarch64-darwin"];
      perSystem = {
        pkgs,
        ...
      }: {
        devShells.default = pkgs.mkShell {
          name = "marimo-dashboard";
          packages = [pkgs.opencode];
          TY_UV = "scripts";
        };

        formatter = pkgs.alejandra;
      };
    };
}
