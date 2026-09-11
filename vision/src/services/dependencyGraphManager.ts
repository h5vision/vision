import * as vscode from 'vscode';

import { DependencyGraph, GraphStatus, GraphProgress } from '../types/dependencyGraph';
import { DependencyGraphService } from './dependencyGraphService';
import { GitService } from './gitService';
import { waitUntil } from '../utils/wait';

export class DependencyGraphManager {

    private graph:
        DependencyGraph | undefined;

    private progress: GraphProgress = { 
        status: 'idle',
        current: 0,
        total: 0,
        message: '분석 대기 중'
    };

    public getProgress(): GraphProgress {
        return this.progress;
    }

    private initialized = false;
    private initializePromise?: Promise<void>;

    private readonly _onStatusChanged = new vscode.EventEmitter<GraphProgress>();

    public readonly onStatusChanged = this._onStatusChanged.event;

    constructor(
        private readonly graphService:
            DependencyGraphService,
        private readonly gitService: GitService
    ) {}

    private setProgress(
        status: GraphStatus,
        message: string,
        current = this.progress.current,
        total = this.progress.total
    ): void {

        this.progress = {
            status,
            current,
            total,
            message
        };

        this._onStatusChanged.fire(
            this.progress
        );
    }

    /**
     * Repository가 준비된 후 호출
     */
    public initialize(): Promise<void> {

        if (!this.initializePromise) {
            this.initializePromise = this.doInitialize();
        }
        return this.initializePromise;
    }

    private async doInitialize(): Promise<void> {

        if (this.initialized) { return; }

        await this.gitService.initialize();
        let gitCommit = await waitUntil(()=>this.gitService.getCurrentCommit(), 10000, 100);
        if (!gitCommit) { 
            gitCommit = 'None';
        }

        this.initialized = true;
        this.setProgress('building [Node]', '프로젝트 구조 분석 중...');

        const saved = await this.graphService.load();
        
        try {
            /*
            * 최초 생성
            */
            if (!saved) {
                console.log('[DependencyGraph] Creating graph...');

                this.graph = await this.graphService.build(gitCommit, (status, current, total) => {
                    this.setProgress(
                        status,
                        '프로젝트 구조 분석 중...',
                        current,
                        total
                    );
                });

                await this.graphService.save(this.graph);

                this.setProgress('ready', '프로젝트 구조 분석 완료');
                return;
            }

            /*
            * Git HEAD 동일
            */
            if ( saved.gitCommit === gitCommit) {
                if (gitCommit === 'None') {
                    vscode.window.showWarningMessage(
                        "Git repository가 없습니다. Indexing 및 Chat 기능을 사용하기 위해서는 Git repository가 필요합니다."
                    );

                    const answer = await vscode.window.showInformationMessage(
                        `그래프를 새로 생성할까요? 마지막 생성시간: ${saved.generatedAt}`,
                        '네', '아니오'
                    );

                    if (answer !== '네') {
                        console.log('[DependencyGraph] Graph is outdated.');
                        this.graph = saved;
                        this.setProgress('ready', `Created At: ${saved.generatedAt}`);
                        return;
                    }

                    console.log('[DependencyGraph] Recreating graph...');

                    this.graph = await this.graphService.build(gitCommit, (status, current, total) => {
                        this.setProgress(
                            status,
                            '프로젝트 구조 분석 중...',
                            current,
                            total
                        );
                    });

                    await this.graphService.save(this.graph);

                    this.setProgress('ready', '프로젝트 구조 분석 완료');
                    return;
                }

                console.log('[DependencyGraph] Graph is up to date.');
                this.graph = saved;
                this.setProgress('ready', '프로젝트 구조 분석 최신 상태');
                return;
            }

            /*
            * Git 변경 감지
            */
            console.log('[DependencyGraph] Git changed. Updating graph...');
            const changedFiles = await this.getChangedFiles();

            /*
            * 변경된 파일만 갱신
            */
            this.graph = await this.graphService.updateFiles(
                saved,
                changedFiles,
                gitCommit, 
                (status, current, total) => {
                    this.setProgress(
                        status,
                        '변경된 파일 분석 중...',
                        current,
                        total
                    );
                }
            );
            await this.graphService.save(this.graph);
            this.setProgress('ready', '프로젝트 구조 분석 최신 상태');
        } catch (error) {
            console.error('[DependencyGraph] Error updating graph:', error);
            this.setProgress('error', '프로젝트 구조 분석 실패');
        }
    }

    /**
     * 현재 Graph 반환
     */
    public getGraph(): DependencyGraph | undefined {
        return this.graph;
    }

    /**
     * Git에서 변경된 파일 목록 가져오기
     */
    private async getChangedFiles():
        Promise<string[]> {
        
        if (!this.gitService.hasChanges()) { return []; }

        const changes = this.gitService.getWorkingTreeFiles();

        return changes.map(
            (change: any) =>
                vscode.workspace.asRelativePath(
                    change.uri,
                    false
                )
        );
    }
}