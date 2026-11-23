// A font file imported from JS is its address after the build (Turbopack), e.g. for <link rel="preload">.
declare module "*.woff2" {
  const src: string;
  export default src;
}
