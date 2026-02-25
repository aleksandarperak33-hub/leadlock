import { Helmet } from 'react-helmet-async';

const SITE_NAME = 'LeadLock';
const BASE_URL = 'https://leadlock.org';
const DEFAULT_DESCRIPTION =
  'Respond to every lead in under 60 seconds with AI-powered SMS. LeadLock qualifies leads, books appointments, and integrates with your CRM. Built for home services contractors.';

export default function SEO({ title, description = DEFAULT_DESCRIPTION, path = '' }) {
  const fullTitle = title ? `${title} | ${SITE_NAME}` : `${SITE_NAME} - AI Speed-to-Lead for Home Services`;
  const url = `${BASE_URL}${path}`;

  return (
    <Helmet>
      <title>{fullTitle}</title>
      <meta name="description" content={description} />
      <link rel="canonical" href={url} />

      <meta property="og:title" content={fullTitle} />
      <meta property="og:description" content={description} />
      <meta property="og:url" content={url} />
      <meta property="og:type" content="website" />
      <meta property="og:image" content={`${BASE_URL}/og-image.png`} />
      <meta property="og:site_name" content={SITE_NAME} />

      <meta name="twitter:card" content="summary_large_image" />
      <meta name="twitter:title" content={fullTitle} />
      <meta name="twitter:description" content={description} />
    </Helmet>
  );
}
