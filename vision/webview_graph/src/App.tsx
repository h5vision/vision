import DependencyGraph from './components/DependencyGraph';

interface AppProps {
  vscode: ReturnType<typeof acquireVsCodeApi>
}

function App({ vscode }: AppProps) {
    return (
        <div
            style={{
                width: '100vw',
                height: '100vh'
            }}
        >
            <DependencyGraph vscode={vscode} />
        </div>
    );
}

export default App;