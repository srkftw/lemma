import Lemma.Compiler.KernelExport

/-! Host-only literal exporter check. It tests the emitted source name, rather
than weakening complete-object equality or importing a target test root. -/
open Lemma.Compiler.DeploymentCatalog
open Lemma.Compiler.KernelExport

#eval do
  for configuration in ["lemmasim-notebook", "lemmasim-initialize", "lemmasim-isolation-development"] do
    let images ← IO.ofExcept (imagesFor configuration)
    let notebook ← IO.ofExcept (imageFor configuration "notebook")
    let store ← IO.ofExcept (imageFor configuration "store")
    unless llvmModuleSourceName configuration "user" (some notebook) ==
        "Lemma lemmasim-virt/0.1.0 user Lemma.Applications.Notebook.main" do
      throw (IO.userError "notebook source name depends on its deployment")
    unless llvmModuleSourceName configuration "user" (some store) ==
        "Lemma lemmasim-virt/0.1.0 user Lemma.Services.Store.Server.main" do
      throw (IO.userError "store source name depends on its deployment")
    unless images.size == (if configuration == "lemmasim-isolation-development" then 3 else 2) do
      throw (IO.userError "source identity fixture changed the deployment catalog")
    for role in ["kernel", "firmware"] do
      unless llvmModuleSourceName configuration role (some notebook) == "Lemma " ++ configuration ++ " " ++ role do
        throw (IO.userError "Lemmasim source-name selection escaped the User role")
  let historical ← IO.ofExcept (imageFor "service-normal" "server")
  unless llvmModuleSourceName "service-normal" "user" (some historical) == "Lemma service-normal user" do
    throw (IO.userError "historical service source identity changed")
  unless llvmModuleSourceName "normal" "user" == "Lemma normal user" do
    throw (IO.userError "historical singleton source identity changed")
  unless llvmModuleSourceName "lemmasim-notebook" "user" == "Lemma lemmasim-notebook user" do
    throw (IO.userError "missing catalog image fabricated a source identity")
  let isolated ← IO.ofExcept (imageFor "lemmasim-isolation-development" "isolation")
  unless llvmModuleSourceName "lemmasim-isolation-development" "user" (some isolated) ==
      "Lemma lemmasim-virt/0.1.0 user Lemma.User.Development.NotebookIsolation.main" do
    throw (IO.userError "isolated client source identity aliases ordinary production code")
  IO.println "LEMMASIM_USER_SOURCE_IDENTITY:PASS literal roots/configurations; historical and non-User names unchanged"
