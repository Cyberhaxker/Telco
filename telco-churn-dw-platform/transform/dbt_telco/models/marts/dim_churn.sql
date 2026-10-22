{{ config(post_hook=["{{ add_primary_key('churn_key') }}"]) }}
select * from (values
    (1, 0::smallint, 'No'::varchar(3)),
    (2, 1::smallint, 'Yes'::varchar(3))
) as t(churn_key, churn_flag, churn_label)
