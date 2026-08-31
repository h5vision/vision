import { useEffect, useMemo, useState } from 'react';

import {
    ReactFlow,
    Background,
    Controls,
    MiniMap,
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

function DependencyGraph({
    vscode,
}: DependencyGraphProps) {

    const [graphData, setGraphData] =
        useState<GraphData | null>(null);

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

        const nodes = graphData.nodes.map((node) => ({
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
        }));

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
    }, [graphData]);

    return (
        <ReactFlow
            colorMode={theme}
            nodes={layout.nodes}
            edges={layout.edges}
            attributionPosition="top-left"
        >
            <Background />
            <Controls />
            <MiniMap />
        </ReactFlow>
    );
}

export default DependencyGraph;