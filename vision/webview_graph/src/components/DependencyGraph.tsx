import { useEffect, useMemo, useState } from 'react';

import {
    ReactFlow,
    ReactFlowProvider,
    Background,
    Controls,
    MiniMap,
    useReactFlow,
} from '@xyflow/react';

import '@xyflow/react/dist/style.css';

import { createLayout } from './graphLayout';

interface VSCodeApi {
    postMessage(message: unknown): void;
    getState(): unknown;
    setState(state: unknown): unknown;
}

interface DependencyGraphProps {
    vscode: VSCodeApi;
}

interface GraphNode {
    id: string;
    path: string;
    label: string;
    language: string;
}

interface GraphEdge {
    id: string;
    source: string;
    target: string;
    type: string;
}

interface GraphData {
    version: number;
    gitCommit: string;
    generatedAt: string;
    nodes: GraphNode[];
    edges: GraphEdge[];
}

function getVSCodeTheme(): 'light' | 'dark' {
    return document.body.classList.contains('vscode-light')
        ? 'light'
        : 'dark';
}

function DependencyGraphInner({
    vscode,
}: DependencyGraphProps) {

    const { fitView } = useReactFlow();

    const [graphData, setGraphData] =
        useState<GraphData | null>(null);

    const [highlightedPaths, setHighlightedPaths] =
        useState<Set<string>>(new Set());

    const [theme, setTheme] = useState<'light' | 'dark'>(
        getVSCodeTheme()
    );

    useEffect(() => {
        const observer = new MutationObserver(() => {
            setTheme(getVSCodeTheme());
        });

        observer.observe(document.body, {
            attributes: true,
            attributeFilter: ['class'],
        });

        return () => {
            observer.disconnect();
        };
    }, []);

    useEffect(() => {
        const handleMessage = (
            event: MessageEvent
        ) => {
            const message = event.data;

            if (message.type === 'graphData') {
                setGraphData(message.data);
            }

            if (message.type === 'highlightSources') {
                setHighlightedPaths(new Set(message.paths ?? []));
            }
        };

        window.addEventListener(
            'message',
            handleMessage
        );

        vscode.postMessage({
            type: 'ready',
        });

        return () => {
            window.removeEventListener(
                'message',
                handleMessage
            );
        };
    }, [vscode]);

    const layout = useMemo(() => {
        if (!graphData) {
            return {
                nodes: [],
                edges: [],
            };
        }

        const nodes = graphData.nodes.map((node) => {
            const isHighlighted = highlightedPaths.has(node.path);

            return {
                id: node.id,

                data: {
                    label: node.label,
                    path: node.path,
                    language: node.language,
                },

                position: {
                    x: 0,
                    y: 0,
                },

                style: isHighlighted
                    ? {
                        background: '#ffd54f',
                        border: '2px solid #f57f17',
                        color: '#1a1a1a',
                    }
                    : undefined,
            };
        });

        const edges = graphData.edges.map((edge) => ({
            id: edge.id,
            source: edge.source,
            target: edge.target,
            label: edge.type,
        }));

        return createLayout(
            nodes,
            edges
        );
    }, [graphData, highlightedPaths]);

    useEffect(() => {
        if (!highlightedPaths.size || !layout.nodes.length) {
            return;
        }

        const highlightedNodeIds = layout.nodes
            .filter((node) => highlightedPaths.has(node.data.path))
            .map((node) => ({ id: node.id }));

        if (!highlightedNodeIds.length) {
            return;
        }

        fitView({
            nodes: highlightedNodeIds,
            duration: 500,
            padding: 0.3,
        });
    }, [layout.nodes, highlightedPaths, fitView]);

    return (
        <ReactFlow
            colorMode={theme}
            nodes={layout.nodes}
            edges={layout.edges}
            attributionPosition="top-left"
            onNodeClick={(_, node) => {
                vscode.postMessage({
                    type: 'openFile',
                    path: node.data.path,
                });
            }}
        >
            <Background />
            <Controls />
            <MiniMap />
        </ReactFlow>
    );
}

function DependencyGraph(props: DependencyGraphProps) {
    return (
        <ReactFlowProvider>
            <DependencyGraphInner {...props} />
        </ReactFlowProvider>
    );
}

export default DependencyGraph;