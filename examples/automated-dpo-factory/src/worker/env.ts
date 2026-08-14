export interface AssetsBinding {
  fetch(request: Request): Promise<Response>;
}

export interface Env {
  ASSETS: AssetsBinding;
  RAMEN_API_KEY: string;
  OPENAI_API_KEY: string;
}
