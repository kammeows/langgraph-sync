import * as vscode from 'vscode';
import * as child_process from 'child_process';
import * as path from 'path';
import * as http from 'http';
import * as fs from 'fs';

let fastapiProcess: child_process.ChildProcess | null = null;
const SERVER_PORT = 8000;

export function activate(context: vscode.ExtensionContext) {
    console.log('LangGraph Sync Visual Builder Extension is active.');

    // Register open command
    let openDisposable = vscode.commands.registerCommand('langgraph-sync.openVisualBuilder', async () => {
        const workspaceFolders = vscode.workspace.workspaceFolders;
        if (!workspaceFolders || workspaceFolders.length === 0) {
            vscode.window.showErrorMessage('Please open a workspace project first.');
            return;
        }
        const projectRoot = workspaceFolders[0].uri.fsPath;

        // Verify/Setup langgraph.json configuration
        const hasConfig = await checkAndSetupLanggraphConfig(projectRoot);
        if (!hasConfig) {
            return; // Exit early if user cancelled or no python files
        }

        // Start FastAPI server if not running
        const started = await startBackendServer(context);
        if (!started) {
            return;
        }

        // Open the builder in the external system browser
        const url = vscode.Uri.parse(`http://localhost:${SERVER_PORT}`);
        await vscode.env.openExternal(url);
    });

    // Register stop command
    let stopDisposable = vscode.commands.registerCommand('langgraph-sync.stopVisualBuilder', async () => {
        stopBackendServer();
        vscode.window.showInformationMessage('LangGraph Visual Builder backend server stopped.');
    });

    context.subscriptions.push(openDisposable, stopDisposable);
}

export function deactivate() {
    stopBackendServer();
}

let lastStderr = '';

async function checkAndSetupLanggraphConfig(projectRoot: string): Promise<boolean> {
    const configPath = path.join(projectRoot, 'langgraph.json');
    if (fs.existsSync(configPath)) {
        return true;
    }

    // Search for python files in workspace folder
    const pythonFiles = await vscode.workspace.findFiles('**/*.py', '**/node_modules/**');
    if (pythonFiles.length === 0) {
        vscode.window.showErrorMessage('No "langgraph.json" or Python files found in this workspace. Please open a Python LangGraph project first.');
        return false;
    }

    // Ask if they want to create a langgraph.json automatically
    const selection = await vscode.window.showInformationMessage(
        'No "langgraph.json" configuration file was found in your workspace root. Would you like to automatically generate one?',
        'Yes, generate default',
        'No, cancel'
    );

    if (selection !== 'Yes, generate default') {
        return false;
    }

    let selectedFile = 'agent.py';
    let selectedGraphVar = 'graph';

    // Scan python files for StateGraph definitions to be smart
    for (const fileUri of pythonFiles) {
        try {
            const content = fs.readFileSync(fileUri.fsPath, 'utf8');
            if (content.includes('StateGraph') || content.includes('create_agent') || content.includes('create_react_agent')) {
                const relativePath = path.relative(projectRoot, fileUri.fsPath).replace(/\\/g, '/');
                selectedFile = relativePath;
                
                const compileMatch = content.match(/(\w+)\s*=\s*(?:\w+\.compile|create_agent|create_react_agent)\s*\(/);
                if (compileMatch) {
                    selectedGraphVar = compileMatch[1];
                }
                break;
            }
        } catch (e) {
            // Ignore read errors
        }
    }

    // Create the default langgraph.json
    const defaultJson = {
        "graphs": {
            "default": `./${selectedFile}:${selectedGraphVar}`
        }
    };

    try {
        fs.writeFileSync(configPath, JSON.stringify(defaultJson, null, 2), 'utf8');
        vscode.window.showInformationMessage(`Successfully generated langgraph.json pointing to ${selectedFile}:${selectedGraphVar}`);
        return true;
    } catch (err: any) {
        vscode.window.showErrorMessage(`Failed to create langgraph.json: ${err.message}`);
        return false;
    }
}

async function setupPrivateVenv(context: vscode.ExtensionContext): Promise<string | null> {
    const globalStoragePath = context.globalStorageUri.fsPath;
    if (!fs.existsSync(globalStoragePath)) {
        fs.mkdirSync(globalStoragePath, { recursive: true });
    }

    const venvDir = path.join(globalStoragePath, 'venv');
    const isWindows = process.platform === 'win32';
    const venvPython = isWindows
        ? path.join(venvDir, 'Scripts', 'python.exe')
        : path.join(venvDir, 'bin', 'python');

    // Check if venv python and key packages are already installed and working
    if (fs.existsSync(venvPython)) {
        try {
            const check = child_process.spawnSync(venvPython, ['-c', 'import libcst, fastapi, uvicorn, requests, google.genai, multipart'], { encoding: 'utf8' });
            if (check.status === 0) {
                console.log(`Private venv verified successfully: ${venvPython}`);
                return venvPython;
            }
        } catch (e) {
            console.log('Verification failed, recreating environment...', e);
        }
    }

    // Find system python
    let systemPython = isWindows ? 'python' : 'python3';
    try {
        const checkSystem = child_process.spawnSync(systemPython, ['--version'], { encoding: 'utf8' });
        if (checkSystem.status !== 0) {
            if (isWindows) {
                const pyCheck = child_process.spawnSync('py', ['--version'], { encoding: 'utf8' });
                if (pyCheck.status === 0) {
                    systemPython = 'py';
                } else {
                    vscode.window.showErrorMessage('Python not found in system PATH. Please install Python 3.9+ to run the visual builder.');
                    return null;
                }
            } else {
                vscode.window.showErrorMessage('Python 3 not found in system PATH. Please install Python 3.9+ to run the visual builder.');
                return null;
            }
        }
    } catch (err) {
        vscode.window.showErrorMessage('Python not found in system PATH. Please install Python 3.9+ to run the visual builder.');
        return null;
    }

    // Create venv and install dependencies
    try {
        await vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: "LangGraph Sync Visual Builder Setup",
            cancellable: false
        }, async (progress) => {
            progress.report({ message: "Creating private virtual environment (one-time setup)..." });
            const createResult = child_process.spawnSync(systemPython, ['-m', 'venv', 'venv'], { cwd: globalStoragePath });
            if (createResult.status !== 0) {
                const stderr = createResult.stderr?.toString();
                const stdout = createResult.stdout?.toString();
                const errorObj = createResult.error?.message;
                const detailedError = [
                    errorObj ? `Process Error: ${errorObj}` : '',
                    stderr ? `Stderr: ${stderr.trim()}` : '',
                    stdout ? `Stdout: ${stdout.trim()}` : ''
                ].filter(Boolean).join('\n');
                throw new Error(detailedError || 'Unknown venv creation failure');
            }

            progress.report({ message: "Installing backend libraries (libcst, fastapi, uvicorn, requests, google-genai, python-multipart)..." });
            const installResult = child_process.spawnSync(venvPython, ['-m', 'pip', 'install', 'libcst', 'fastapi', 'uvicorn', 'python-dotenv', 'requests', 'google-genai', 'python-multipart'], { cwd: globalStoragePath });
            if (installResult.status !== 0) {
                const stderr = installResult.stderr?.toString();
                const stdout = installResult.stdout?.toString();
                const errorObj = installResult.error?.message;
                const detailedError = [
                    errorObj ? `Process Error: ${errorObj}` : '',
                    stderr ? `Stderr: ${stderr.trim()}` : '',
                    stdout ? `Stdout: ${stdout.trim()}` : ''
                ].filter(Boolean).join('\n');
                throw new Error(detailedError || 'Unknown installation failure');
            }
        });

        if (fs.existsSync(venvPython)) {
            vscode.window.showInformationMessage('LangGraph Sync backend environment initialized successfully!');
            return venvPython;
        }
    } catch (err: any) {
        vscode.window.showErrorMessage(`Failed to set up private Python environment:\n${err.message}`);
        return null;
    }

    return null;
}

async function findPythonPath(context: vscode.ExtensionContext, projectRoot: string): Promise<string | null> {
    // 1. Try to get user configured custom python path from vscode settings
    const configPath = vscode.workspace.getConfiguration('langgraph-sync').get<string>('pythonPath');
    if (configPath && fs.existsSync(configPath)) {
        console.log(`Using Python from configuration: ${configPath}`);
        return configPath;
    }

    const isWindows = process.platform === 'win32';
    const venvNames = ['venv', '.venv', 'env', '.env'];

    // 2. Scan project root and parent directories (up to 3 levels) for a local venv
    let currentDir = projectRoot;
    for (let depth = 0; depth < 3; depth++) {
        for (const name of venvNames) {
            const venvPython = isWindows
                ? path.join(currentDir, name, 'Scripts', 'python.exe')
                : path.join(currentDir, name, 'bin', 'python');
            
            if (fs.existsSync(venvPython)) {
                // Verify if dependencies are installed in this local venv
                const check = child_process.spawnSync(venvPython, ['-c', 'import libcst, fastapi, uvicorn'], { encoding: 'utf8' });
                if (check.status === 0) {
                    console.log(`Using validated local venv: ${venvPython}`);
                    return venvPython;
                }
            }
        }
        const parentDir = path.dirname(currentDir);
        if (parentDir === currentDir) {
            break;
        }
        currentDir = parentDir;
    }

    // 3. Check/Setup our managed private virtual environment (Zero-config out of the box)
    const privateVenv = await setupPrivateVenv(context);
    if (privateVenv) {
        return privateVenv;
    }

    // 4. Fallback to known development workspace venv if it exists
    const devVenvPython = isWindows
        ? 'D:\\uni\\agentic_ai\\venv\\Scripts\\python.exe'
        : 'D:/uni/agentic_ai/venv/bin/python';
    if (fs.existsSync(devVenvPython)) {
        console.log(`Using development venv python fallback: ${devVenvPython}`);
        return devVenvPython;
    }

    // 5. Try to get Python path from the ms-python extension if active
    try {
        const pythonExtension = vscode.extensions.getExtension('ms-python.python');
        if (pythonExtension) {
            if (!pythonExtension.isActive) {
                await pythonExtension.activate();
            }
            const execDetails = pythonExtension.exports?.settings?.getExecutionDetails?.();
            const execPath = execDetails?.execCommand?.[0];
            if (execPath && fs.existsSync(execPath)) {
                console.log(`Using Python from python extension: ${execPath}`);
                return execPath;
            }
        }
    } catch (e) {
        console.error('Error querying python extension:', e);
    }

    return null;
}

async function startBackendServer(context: vscode.ExtensionContext): Promise<boolean> {
    if (fastapiProcess) {
        return true; // Already running
    }

    // Check if server is already running on port 8000
    const isAlive = await pingServer(SERVER_PORT);
    if (isAlive) {
        console.log(`Port ${SERVER_PORT} is already active. Reusing the existing server process.`);
        return true;
    }

    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders || workspaceFolders.length === 0) {
        vscode.window.showErrorMessage('Please open a workspace project first.');
        return false;
    }

    const projectRoot = workspaceFolders[0].uri.fsPath;
    // Resolve the parser script relative to the extension folder context
    const pythonScript = path.join(context.extensionPath, 'server', 'server.py');

    // Attempt to locate python executable
    const pythonPath = await findPythonPath(context, projectRoot);
    if (!pythonPath) {
        vscode.window.showErrorMessage('Could not find or configure a suitable Python environment containing libcst and fastapi.');
        return false;
    }
    console.log(`Launching backend server via: ${pythonPath} ${pythonScript}`);

    lastStderr = '';

    fastapiProcess = child_process.spawn(pythonPath, [pythonScript], {
        cwd: projectRoot,
        env: { 
            ...process.env, 
            PORT: String(SERVER_PORT),
            WORKSPACE_ROOT: projectRoot
        }
    });

    fastapiProcess.stdout?.on('data', (data) => {
        console.log(`[FastAPI stdout]: ${data}`);
    });

    fastapiProcess.stderr?.on('data', (data) => {
        const str = data.toString();
        console.error(`[FastAPI stderr]: ${str}`);
        lastStderr += str;
    });

    fastapiProcess.on('close', (code) => {
        console.log(`FastAPI backend server exited with code ${code}`);
        fastapiProcess = null;
    });

    // Wait a brief moment for startup and ping
    for (let i = 0; i < 15; i++) {
        await sleep(500);
        if (await pingServer(SERVER_PORT)) {
            vscode.window.showInformationMessage('LangGraph Visual Builder backend server started.');
            return true;
        }
        if (!fastapiProcess) {
            break; // Exited early
        }
    }

    // If server failed to start, report the captured stderr
    const errorDetails = lastStderr ? `\n\nError output:\n${lastStderr.trim()}` : '';
    vscode.window.showErrorMessage(`Failed to start LangGraph Visual Builder backend server.
Workspace Root: ${projectRoot}
Python Executable: ${pythonPath}
Script Path: ${pythonScript}${errorDetails}`);
    return false;
}

function stopBackendServer() {
    if (fastapiProcess) {
        console.log('Stopping FastAPI backend server...');
        fastapiProcess.kill();
        fastapiProcess = null;
    }
}

function pingServer(port: number): Promise<boolean> {
    return new Promise((resolve) => {
        const req = http.get(`http://localhost:${port}/api/graphs`, (res) => {
            resolve(res.statusCode === 200);
        });
        req.on('error', () => {
            resolve(false);
        });
        req.setTimeout(500, () => {
            req.destroy();
            resolve(false);
        });
    });
}

function getWebviewContent(port: number): string {
    return `<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>LangGraph Builder</title>
        <style>
            html, body, iframe {
                margin: 0;
                padding: 0;
                width: 100%;
                height: 100%;
                border: none;
                overflow: hidden;
                background-color: #1e1e1e;
            }
        </style>
    </head>
    <body>
        <iframe src="http://localhost:${port}"></iframe>
    </body>
    </html>`;
}

function sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
}
