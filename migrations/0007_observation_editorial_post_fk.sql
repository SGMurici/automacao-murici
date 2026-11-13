-- Preserve referential integrity for editorial observations linked to posts.
-- Existing orphan rows must be reconciled before this migration can be applied.
ALTER TABLE engagement_post_observations
    ADD CONSTRAINT engagement_post_observations_editorial_post_id_fkey
    FOREIGN KEY (editorial_post_id)
    REFERENCES editorial_posts(id)
    ON DELETE SET NULL;
