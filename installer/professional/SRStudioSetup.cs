using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32;

[assembly: AssemblyTitle("SR Studio Setup")]
[assembly: AssemblyProduct("SR Studio")]
[assembly: AssemblyCompany("SR")]
[assembly: AssemblyDescription("Instalador online oficial do SR Studio")]
[assembly: AssemblyVersion("1.0.0.0")]
[assembly: AssemblyFileVersion("1.0.0.0")]

namespace SRStudioSetup
{
    internal static class Program
    {
        internal const string RepoBase = "https://raw.githubusercontent.com/lucasamaralvida3-del/SR-STUDIO/main";
        internal const string StableManifestUrl = RepoBase + "/stable/manifest.json";
        internal const string LauncherManifestUrl = RepoBase + "/manifests/launcher.json";
        internal const string BootstrapUrl = RepoBase + "/launcher/files/SRStudioBootstrap.ps1";
        internal const string IconUrl = RepoBase + "/staging/logo_update/source/SR_Studio.ico";

        [STAThread]
        private static int Main(string[] args)
        {
            ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;

            try
            {
                if (args != null && args.Length > 0)
                {
                    string command = (args[0] ?? "").Trim().ToLowerInvariant();
                    if (command == "/launch" || command == "--launch")
                        return OnlineInstaller.LaunchInstalled();
                    if (command == "/selftest" || command == "--selftest")
                        return OnlineInstaller.SelfTest();
                    if (command == "/uninstall" || command == "--uninstall")
                        return OnlineInstaller.UninstallInteractive();
                }

                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                Application.Run(new SetupForm());
                return 0;
            }
            catch (Exception ex)
            {
                try { MessageBox.Show(ex.Message, "SR Studio Setup", MessageBoxButtons.OK, MessageBoxIcon.Error); }
                catch { }
                return 1;
            }
        }
    }

    internal sealed class StableInfo
    {
        public string Version;
        public string Label;
        public string BundleUrl;
        public string Sha256;
        public long Size;
    }

    internal static class OnlineInstaller
    {
        internal static readonly string Root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "SRStudio");
        internal static readonly string LauncherDir = Path.Combine(Root, "Launcher");
        internal static readonly string ConfigDir = Path.Combine(Root, "Config");
        internal static readonly string AssetsDir = Path.Combine(Root, "Assets");
        internal static readonly string LogsDir = Path.Combine(Root, "Logs");
        internal static readonly string CacheDir = Path.Combine(Root, "Cache");
        internal static readonly string InstalledExe = Path.Combine(LauncherDir, "SRStudio.exe");
        internal static readonly string BootstrapPath = Path.Combine(LauncherDir, "SRStudioBootstrap.ps1");
        internal static readonly string LauncherPath = Path.Combine(LauncherDir, "SRStudioLauncher.ps1");
        internal static readonly string LocalIconPath = Path.Combine(AssetsDir, "SR_Studio.ico");

        private static JavaScriptSerializer Json = new JavaScriptSerializer();

        internal static StableInfo GetStableInfo()
        {
            string json = DownloadString(Program.StableManifestUrl);
            Dictionary<string, object> root = Json.DeserializeObject(json) as Dictionary<string, object>;
            if (root == null) throw new Exception("Manifesto Stable inválido.");
            string format = GetString(root, "format");
            if (format != "SRSTUDIO_HYBRID_BUNDLE_1")
                throw new Exception("O repositório Stable está em um formato não suportado: " + format);

            Dictionary<string, object> bundle = null;
            object bundleObj;
            if (root.TryGetValue("bundle", out bundleObj)) bundle = bundleObj as Dictionary<string, object>;
            if (bundle == null) throw new Exception("O manifesto Stable não contém o bloco bundle.");

            StableInfo info = new StableInfo();
            info.Version = GetString(root, "version");
            info.Label = GetString(root, "release_label");
            info.BundleUrl = GetString(bundle, "url");
            info.Sha256 = GetString(bundle, "sha256").ToLowerInvariant();
            info.Size = GetLong(bundle, "size");
            if (String.IsNullOrWhiteSpace(info.Version) || String.IsNullOrWhiteSpace(info.BundleUrl) || info.Sha256.Length != 64)
                throw new Exception("Manifesto Stable incompleto.");
            return info;
        }

        internal static void PrepareDirectories()
        {
            Directory.CreateDirectory(Root);
            Directory.CreateDirectory(LauncherDir);
            Directory.CreateDirectory(ConfigDir);
            Directory.CreateDirectory(AssetsDir);
            Directory.CreateDirectory(LogsDir);
            Directory.CreateDirectory(CacheDir);
        }

        internal static void DownloadBootstrap()
        {
            PrepareDirectories();
            DownloadFileAtomic(Program.BootstrapUrl, BootstrapPath);
            if (!File.Exists(BootstrapPath) || new FileInfo(BootstrapPath).Length < 1000)
                throw new Exception("Bootstrap baixado está inválido.");
        }

        internal static string DownloadAndValidateLauncher()
        {
            PrepareDirectories();
            string manifestText = DownloadString(Program.LauncherManifestUrl);
            Dictionary<string, object> manifest = Json.DeserializeObject(manifestText) as Dictionary<string, object>;
            if (manifest == null) throw new Exception("Manifesto do Launcher inválido.");
            string format = GetString(manifest, "format");
            if (format != "SRSTUDIO_LAUNCHER_MANIFEST_1" && format != "SRSTUDIO_LAUNCHER_1")
                throw new Exception("Formato do Launcher não suportado: " + format);

            object filesObj;
            if (!manifest.TryGetValue("files", out filesObj)) throw new Exception("Manifesto do Launcher não contém arquivos.");
            object[] files = filesObj as object[];
            if (files == null || files.Length == 0) throw new Exception("Manifesto do Launcher está vazio.");

            Dictionary<string, object> entry = files[0] as Dictionary<string, object>;
            if (entry == null) throw new Exception("Entrada do Launcher inválida.");
            string source = GetString(entry, "source").Replace('\\', '/');
            string expectedSha = GetString(entry, "sha256").ToLowerInvariant();
            long expectedSize = GetLong(entry, "size");
            if (String.IsNullOrWhiteSpace(source) || expectedSha.Length != 64) throw new Exception("Dados de validação do Launcher ausentes.");

            string temp = LauncherPath + ".download";
            if (File.Exists(temp)) File.Delete(temp);
            DownloadFile(Program.RepoBase + "/" + source, temp);
            if (expectedSize > 0 && new FileInfo(temp).Length != expectedSize)
            {
                File.Delete(temp);
                throw new Exception("Tamanho do Launcher não confere com o manifesto oficial.");
            }
            string actualSha = Sha256(temp);
            if (!String.Equals(actualSha, expectedSha, StringComparison.OrdinalIgnoreCase))
            {
                File.Delete(temp);
                throw new Exception("SHA-256 do Launcher não confere com o manifesto oficial.");
            }
            if (File.Exists(LauncherPath)) File.Delete(LauncherPath);
            File.Move(temp, LauncherPath);
            return GetString(manifest, "version");
        }

        internal static void DownloadIcon()
        {
            try { DownloadFileAtomic(Program.IconUrl, LocalIconPath); }
            catch { }
        }

        internal static void WriteStableConfig()
        {
            PrepareDirectories();
            string text = "{\r\n" +
                "  \"schema\": 3,\r\n" +
                "  \"channel\": \"stable\",\r\n" +
                "  \"auto_update\": true,\r\n" +
                "  \"repair_on_start\": true,\r\n" +
                "  \"full_repair_every_days\": 7,\r\n" +
                "  \"allow_offline\": true,\r\n" +
                "  \"remote_manifest_base\": \"" + Program.RepoBase + "\",\r\n" +
                "  \"local_repository\": \"\",\r\n" +
                "  \"entrypoint\": \"SR_Studio_Gerador.py\",\r\n" +
                "  \"python_command\": \"\",\r\n" +
                "  \"encartes_cloud_url\": \"http://127.0.0.1:3000\",\r\n" +
                "  \"keep_backups\": 3,\r\n" +
                "  \"connect_timeout_seconds\": 15,\r\n" +
                "  \"download_timeout_seconds\": 600,\r\n" +
                "  \"download_retries\": 3,\r\n" +
                "  \"auto_update_launcher\": true\r\n" +
                "}\r\n";
            File.WriteAllText(Path.Combine(ConfigDir, "launcher.json"), text, new UTF8Encoding(false));
        }

        internal static void InstallSelf()
        {
            PrepareDirectories();
            string current = Application.ExecutablePath;
            if (!String.Equals(Path.GetFullPath(current), Path.GetFullPath(InstalledExe), StringComparison.OrdinalIgnoreCase))
            {
                string temp = InstalledExe + ".new";
                File.Copy(current, temp, true);
                if (File.Exists(InstalledExe)) File.Delete(InstalledExe);
                File.Move(temp, InstalledExe);
            }
        }

        internal static void CreateShortcuts(bool desktop)
        {
            string icon = File.Exists(LocalIconPath) ? LocalIconPath : InstalledExe;
            string startDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.StartMenu), "Programs", "SR Studio");
            Directory.CreateDirectory(startDir);
            CreateShortcut(Path.Combine(startDir, "SR Studio.lnk"), InstalledExe, "/launch", icon, "Abrir SR Studio");
            CreateShortcut(Path.Combine(startDir, "Desinstalar SR Studio.lnk"), InstalledExe, "/uninstall", icon, "Desinstalar SR Studio");
            if (desktop)
                CreateShortcut(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "SR Studio.lnk"), InstalledExe, "/launch", icon, "Abrir SR Studio");
        }

        internal static void RegisterUninstall()
        {
            try
            {
                using (RegistryKey key = Registry.CurrentUser.CreateSubKey(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\SRStudio"))
                {
                    if (key == null) return;
                    key.SetValue("DisplayName", "SR Studio");
                    key.SetValue("DisplayIcon", InstalledExe);
                    key.SetValue("Publisher", "SR");
                    key.SetValue("InstallLocation", Root);
                    key.SetValue("UninstallString", "\"" + InstalledExe + "\" /uninstall");
                    key.SetValue("NoModify", 1, RegistryValueKind.DWord);
                    key.SetValue("NoRepair", 1, RegistryValueKind.DWord);
                }
            }
            catch { }
        }

        internal static int RunBootstrap(bool noLaunch)
        {
            if (!File.Exists(BootstrapPath)) DownloadBootstrap();
            string ps = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), @"WindowsPowerShell\v1.0\powershell.exe");
            if (!File.Exists(ps)) ps = "powershell.exe";
            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = ps;
            psi.Arguments = "-NoProfile -ExecutionPolicy Bypass -File \"" + BootstrapPath + "\"" + (noLaunch ? " -NoLaunch" : "");
            psi.WorkingDirectory = LauncherDir;
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;
            psi.WindowStyle = ProcessWindowStyle.Hidden;
            Process p = Process.Start(psi);
            if (p == null) return 1;
            p.WaitForExit();
            return p.ExitCode;
        }

        internal static int LaunchInstalled()
        {
            try
            {
                PrepareDirectories();
                try { DownloadBootstrap(); } catch { if (!File.Exists(BootstrapPath)) throw; }
                int code = RunBootstrap(false);
                if (code != 0)
                {
                    MessageBox.Show("O SR Studio não conseguiu iniciar. Código: " + code + "\n\nLog: " + Path.Combine(LogsDir, "launcher.log"), "SR Studio", MessageBoxButtons.OK, MessageBoxIcon.Error);
                }
                return code;
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message + "\n\nLog: " + Path.Combine(LogsDir, "launcher.log"), "SR Studio", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 1;
            }
        }

        internal static int SelfTest()
        {
            try
            {
                StableInfo stable = GetStableInfo();
                string launcherManifest = DownloadString(Program.LauncherManifestUrl);
                Dictionary<string, object> manifest = Json.DeserializeObject(launcherManifest) as Dictionary<string, object>;
                if (manifest == null || String.IsNullOrWhiteSpace(stable.Version)) return 2;
                object files;
                if (!manifest.TryGetValue("files", out files) || !(files is object[])) return 3;
                return 0;
            }
            catch { return 1; }
        }

        internal static int UninstallInteractive()
        {
            DialogResult result = MessageBox.Show("Deseja desinstalar o SR Studio deste computador?\n\nOs arquivos locais do programa serão removidos.", "Desinstalar SR Studio", MessageBoxButtons.YesNo, MessageBoxIcon.Question);
            if (result != DialogResult.Yes) return 0;
            try
            {
                string desktop = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "SR Studio.lnk");
                if (File.Exists(desktop)) File.Delete(desktop);
                string startDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.StartMenu), "Programs", "SR Studio");
                if (Directory.Exists(startDir)) Directory.Delete(startDir, true);
                try { Registry.CurrentUser.DeleteSubKeyTree(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\SRStudio", false); } catch { }

                string cmd = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "cmd.exe");
                ProcessStartInfo psi = new ProcessStartInfo();
                psi.FileName = cmd;
                psi.Arguments = "/c ping 127.0.0.1 -n 3 >nul & rmdir /s /q \"" + Root + "\"";
                psi.CreateNoWindow = true;
                psi.UseShellExecute = false;
                Process.Start(psi);
                MessageBox.Show("SR Studio removido.", "SR Studio", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return 0;
            }
            catch (Exception ex)
            {
                MessageBox.Show("Não foi possível concluir a desinstalação.\n\n" + ex.Message, "SR Studio", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 1;
            }
        }

        internal static string ReadInstalledVersion()
        {
            try
            {
                string p = Path.Combine(ConfigDir, "installed.json");
                if (!File.Exists(p)) return "";
                Dictionary<string, object> data = Json.DeserializeObject(File.ReadAllText(p, Encoding.UTF8)) as Dictionary<string, object>;
                return data == null ? "" : GetString(data, "version");
            }
            catch { return ""; }
        }

        private static void CreateShortcut(string shortcutPath, string targetPath, string arguments, string iconPath, string description)
        {
            Type shellType = Type.GetTypeFromProgID("WScript.Shell");
            if (shellType == null) throw new Exception("Windows Script Host não está disponível para criar atalhos.");
            object shell = Activator.CreateInstance(shellType);
            object shortcut = null;
            try
            {
                shortcut = shellType.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, shell, new object[] { shortcutPath });
                Type shortcutType = shortcut.GetType();
                shortcutType.InvokeMember("TargetPath", BindingFlags.SetProperty, null, shortcut, new object[] { targetPath });
                shortcutType.InvokeMember("Arguments", BindingFlags.SetProperty, null, shortcut, new object[] { arguments });
                shortcutType.InvokeMember("WorkingDirectory", BindingFlags.SetProperty, null, shortcut, new object[] { Path.GetDirectoryName(targetPath) });
                shortcutType.InvokeMember("Description", BindingFlags.SetProperty, null, shortcut, new object[] { description });
                shortcutType.InvokeMember("IconLocation", BindingFlags.SetProperty, null, shortcut, new object[] { iconPath + ",0" });
                shortcutType.InvokeMember("Save", BindingFlags.InvokeMethod, null, shortcut, null);
            }
            finally
            {
                if (shortcut != null && Marshal.IsComObject(shortcut)) Marshal.FinalReleaseComObject(shortcut);
                if (shell != null && Marshal.IsComObject(shell)) Marshal.FinalReleaseComObject(shell);
            }
        }

        private static string DownloadString(string url)
        {
            using (WebClient wc = NewClient()) return wc.DownloadString(url + (url.Contains("?") ? "&" : "?") + "t=" + DateTimeOffset.UtcNow.ToUnixTimeSeconds());
        }

        private static void DownloadFile(string url, string destination)
        {
            using (WebClient wc = NewClient()) wc.DownloadFile(url + (url.Contains("?") ? "&" : "?") + "t=" + DateTimeOffset.UtcNow.ToUnixTimeSeconds(), destination);
        }

        private static void DownloadFileAtomic(string url, string destination)
        {
            string dir = Path.GetDirectoryName(destination);
            if (!String.IsNullOrWhiteSpace(dir)) Directory.CreateDirectory(dir);
            string temp = destination + ".download";
            if (File.Exists(temp)) File.Delete(temp);
            DownloadFile(url, temp);
            if (File.Exists(destination)) File.Delete(destination);
            File.Move(temp, destination);
        }

        private static WebClient NewClient()
        {
            WebClient wc = new WebClient();
            wc.Encoding = Encoding.UTF8;
            wc.Headers[HttpRequestHeader.UserAgent] = "SRStudioSetup/1.0";
            wc.Headers[HttpRequestHeader.CacheControl] = "no-cache";
            return wc;
        }

        private static string Sha256(string path)
        {
            using (SHA256 sha = SHA256.Create())
            using (FileStream stream = File.OpenRead(path))
            {
                byte[] hash = sha.ComputeHash(stream);
                StringBuilder sb = new StringBuilder(hash.Length * 2);
                for (int i = 0; i < hash.Length; i++) sb.Append(hash[i].ToString("x2"));
                return sb.ToString();
            }
        }

        private static string GetString(Dictionary<string, object> d, string key)
        {
            object v;
            return d != null && d.TryGetValue(key, out v) && v != null ? Convert.ToString(v) : "";
        }

        private static long GetLong(Dictionary<string, object> d, string key)
        {
            object v;
            if (d != null && d.TryGetValue(key, out v) && v != null)
            {
                long x;
                if (Int64.TryParse(Convert.ToString(v), out x)) return x;
            }
            return 0;
        }
    }

    internal sealed class SetupForm : Form
    {
        private Label versionLabel;
        private Label statusLabel;
        private ProgressBar progress;
        private Button installButton;
        private Button cancelButton;
        private CheckBox desktopCheck;
        private CheckBox openCheck;
        private bool busy;
        private StableInfo stable;

        internal SetupForm()
        {
            Text = "SR Studio — Instalação";
            StartPosition = FormStartPosition.CenterScreen;
            FormBorderStyle = FormBorderStyle.FixedSingle;
            MaximizeBox = false;
            MinimizeBox = true;
            ClientSize = new Size(660, 430);
            BackColor = Color.FromArgb(246, 249, 253);
            Font = new Font("Segoe UI", 9F);
            try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { }

            Panel header = new Panel();
            header.Dock = DockStyle.Top;
            header.Height = 118;
            header.BackColor = Color.FromArgb(0, 78, 146);
            Controls.Add(header);

            PictureBox logo = new PictureBox();
            logo.Location = new Point(28, 25);
            logo.Size = new Size(64, 64);
            logo.SizeMode = PictureBoxSizeMode.Zoom;
            try
            {
                Icon appIcon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
                if (appIcon != null) logo.Image = appIcon.ToBitmap();
            }
            catch { }
            header.Controls.Add(logo);

            Label title = new Label();
            title.Text = "SR Studio";
            title.ForeColor = Color.White;
            title.Font = new Font("Segoe UI Semibold", 22F, FontStyle.Bold);
            title.AutoSize = true;
            title.Location = new Point(108, 22);
            header.Controls.Add(title);

            Label subtitle = new Label();
            subtitle.Text = "Instalador oficial online • Canal Stable";
            subtitle.ForeColor = Color.FromArgb(220, 236, 250);
            subtitle.Font = new Font("Segoe UI", 10F);
            subtitle.AutoSize = true;
            subtitle.Location = new Point(111, 70);
            header.Controls.Add(subtitle);

            Label intro = new Label();
            intro.Text = "Este instalador consulta o repositório oficial e instala a versão Stable disponível no momento da instalação.\nFeche o SR Studio antes de continuar.";
            intro.ForeColor = Color.FromArgb(48, 61, 74);
            intro.Location = new Point(30, 143);
            intro.Size = new Size(600, 52);
            Controls.Add(intro);

            versionLabel = new Label();
            versionLabel.Text = "Verificando versão Stable disponível...";
            versionLabel.ForeColor = Color.FromArgb(0, 78, 146);
            versionLabel.Font = new Font("Segoe UI Semibold", 10F, FontStyle.Bold);
            versionLabel.Location = new Point(30, 203);
            versionLabel.Size = new Size(600, 24);
            Controls.Add(versionLabel);

            statusLabel = new Label();
            statusLabel.Text = "Aguardando.";
            statusLabel.ForeColor = Color.FromArgb(86, 98, 110);
            statusLabel.Location = new Point(30, 238);
            statusLabel.Size = new Size(600, 24);
            Controls.Add(statusLabel);

            progress = new ProgressBar();
            progress.Location = new Point(30, 267);
            progress.Size = new Size(600, 18);
            progress.Style = ProgressBarStyle.Continuous;
            Controls.Add(progress);

            desktopCheck = new CheckBox();
            desktopCheck.Text = "Criar atalho na Área de Trabalho";
            desktopCheck.Checked = true;
            desktopCheck.Location = new Point(30, 304);
            desktopCheck.AutoSize = true;
            Controls.Add(desktopCheck);

            openCheck = new CheckBox();
            openCheck.Text = "Abrir o SR Studio ao concluir";
            openCheck.Checked = true;
            openCheck.Location = new Point(30, 332);
            openCheck.AutoSize = true;
            Controls.Add(openCheck);

            installButton = new Button();
            installButton.Text = "INSTALAR";
            installButton.Size = new Size(140, 40);
            installButton.Location = new Point(350, 370);
            installButton.FlatStyle = FlatStyle.Flat;
            installButton.FlatAppearance.BorderSize = 0;
            installButton.BackColor = Color.FromArgb(0, 78, 146);
            installButton.ForeColor = Color.White;
            installButton.Font = new Font("Segoe UI Semibold", 9.5F, FontStyle.Bold);
            installButton.Click += InstallButton_Click;
            Controls.Add(installButton);

            cancelButton = new Button();
            cancelButton.Text = "Cancelar";
            cancelButton.Size = new Size(120, 40);
            cancelButton.Location = new Point(510, 370);
            cancelButton.FlatStyle = FlatStyle.Flat;
            cancelButton.Click += delegate { if (!busy) Close(); };
            Controls.Add(cancelButton);

            Shown += async delegate { await CheckStableAsync(); };
            FormClosing += delegate(object sender, FormClosingEventArgs e) { if (busy) e.Cancel = true; };
        }

        private async Task CheckStableAsync()
        {
            try
            {
                stable = await Task.Run<StableInfo>(delegate { return OnlineInstaller.GetStableInfo(); });
                versionLabel.Text = "Stable disponível: " + stable.Version;
                statusLabel.Text = "Pronto para instalar.";
            }
            catch (Exception ex)
            {
                versionLabel.Text = "Não foi possível consultar a Stable.";
                statusLabel.Text = ex.Message;
            }
        }

        private async void InstallButton_Click(object sender, EventArgs e)
        {
            if (busy) return;
            busy = true;
            installButton.Enabled = false;
            cancelButton.Enabled = false;
            desktopCheck.Enabled = false;
            openCheck.Enabled = false;

            try
            {
                SetProgress(5, "Consultando o repositório Stable...");
                stable = await Task.Run<StableInfo>(delegate { return OnlineInstaller.GetStableInfo(); });
                versionLabel.Text = "Stable selecionada: " + stable.Version;

                SetProgress(15, "Preparando a instalação local...");
                await Task.Run(delegate { OnlineInstaller.PrepareDirectories(); });

                SetProgress(25, "Baixando Bootstrap oficial...");
                await Task.Run(delegate { OnlineInstaller.DownloadBootstrap(); });

                SetProgress(38, "Baixando e validando o Launcher atual...");
                string launcherVersion = await Task.Run<string>(delegate { return OnlineInstaller.DownloadAndValidateLauncher(); });

                SetProgress(50, "Aplicando identidade visual e logo...");
                await Task.Run(delegate { OnlineInstaller.DownloadIcon(); });

                SetProgress(60, "Configurando canal Stable e atualização automática...");
                await Task.Run(delegate { OnlineInstaller.WriteStableConfig(); });

                SetProgress(70, "Criando atalhos do SR Studio...");
                bool createDesktop = desktopCheck.Checked;
                await Task.Run(delegate
                {
                    OnlineInstaller.InstallSelf();
                    OnlineInstaller.CreateShortcuts(createDesktop);
                    OnlineInstaller.RegisterUninstall();
                });

                SetProgress(80, "Baixando a Stable atual e preparando o runtime...");
                int exitCode = await Task.Run<int>(delegate { return OnlineInstaller.RunBootstrap(true); });
                if (exitCode != 0) throw new Exception("O Launcher retornou o código " + exitCode + ". Consulte " + Path.Combine(OnlineInstaller.LogsDir, "launcher.log"));

                SetProgress(100, "Instalação concluída com sucesso.");
                string installed = OnlineInstaller.ReadInstalledVersion();
                if (!String.IsNullOrWhiteSpace(installed)) versionLabel.Text = "Instalado: " + installed + " • Launcher " + launcherVersion;

                installButton.Text = "CONCLUÍDO";
                MessageBox.Show("SR Studio instalado com sucesso.\n\nVersão Stable: " + (String.IsNullOrWhiteSpace(installed) ? stable.Version : installed) + "\n\nO instalador continuará buscando a Stable atual no repositório sempre que for utilizado.", "SR Studio", MessageBoxButtons.OK, MessageBoxIcon.Information);

                if (openCheck.Checked)
                    await Task.Run(delegate { OnlineInstaller.LaunchInstalled(); });

                Close();
            }
            catch (Exception ex)
            {
                SetProgress(progress.Value, "A instalação encontrou um erro.");
                MessageBox.Show(ex.Message + "\n\nLog do Launcher: " + Path.Combine(OnlineInstaller.LogsDir, "launcher.log"), "SR Studio Setup", MessageBoxButtons.OK, MessageBoxIcon.Error);
                installButton.Enabled = true;
                installButton.Text = "TENTAR NOVAMENTE";
                cancelButton.Enabled = true;
                desktopCheck.Enabled = true;
                openCheck.Enabled = true;
            }
            finally
            {
                busy = false;
            }
        }

        private void SetProgress(int value, string text)
        {
            if (value < 0) value = 0;
            if (value > 100) value = 100;
            progress.Value = value;
            statusLabel.Text = text;
            statusLabel.Refresh();
            progress.Refresh();
        }
    }
}
