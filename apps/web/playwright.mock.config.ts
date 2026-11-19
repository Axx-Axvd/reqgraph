// The mock mode of the e2e test (see playwright.config.ts): no Supabase, no API.
import { configFor } from "./playwright.config";

export default configFor(true);
