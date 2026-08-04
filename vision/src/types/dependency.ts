export interface DependencyFile {
    path: string;
    label: string;

    imported: boolean;     // 현재 파일이 사용
    referenced: boolean;   // 현재 파일를 사용

    llmSource?: boolean;
    gitRelated?: boolean;
}