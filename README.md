# Pack Studio

**Pack Studio** est une application de bureau Python/PyQt5 qui génère automatiquement les fichiers `build.bat` et `installer.iss` pour n'importe quel projet PyQt5, afin de le compiler en exécutable puis de le distribuer sous forme d'installateur Windows.

## Présentation

Transformer un projet PyQt5 en programme installable demande généralement d'écrire à la main un script de compilation PyInstaller et un script d'installation Inno Setup, à refaire pour chaque nouveau projet.

Pack Studio supprime cette étape répétitive : vous renseignez les informations de votre application dans une interface graphique, et l'outil produit les fichiers prêts à l'emploi.

## Fonctionnalités

- Génération du fichier `build.bat` pour compiler le projet avec **PyInstaller**.
- Génération du fichier `installer.iss` pour créer l'installateur avec **Inno Setup**.
- Lancement de PyInstaller depuis l'application.
- Lancement d'Inno Setup depuis l'application.
- Interface moderne sombre, de style verre, avec un fond animé et des dégradés cyan/violet.

## Prérequis

- Windows
- Python 3.8
- PyQt5
- [PyInstaller](https://pyinstaller.org/)
- [Inno Setup 7.1.0](https://jrsoftware.org/isdl.php) (version ANSI)

## Installation et utilisation

1. Clonez le dépôt :

   ```bash
   git clone https://github.com/VOTRE-PSEUDO/PackStudio.git
   cd PackStudio
   ```

2. Installez les dépendances :

   ```bash
   pip install PyQt5 pyinstaller
   ```

3. Installez Inno Setup 7.1.0 si ce n'est pas déjà fait.

4. Lancez l'application :

   ```bash
   python PackStudio.py
   ```

5. Dans l'interface :
   1. Renseignez les informations de votre projet (nom, version, script principal, icône, etc.).
   2. Générez `build.bat` et `installer.iss`.
   3. Lancez PyInstaller pour compiler le projet.
   4. Lancez Inno Setup pour créer l'installateur.


## Auteur

**Morsli Hammou**

GitHub : [hammoumorsli](https://github.com/hammoumorsli)
