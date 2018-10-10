from .calculate_bayes_factors import calculate_bayes_factors

# Only this function is supposed to be used publicly.
# The package can be imported by just `import bayes_factors`.
__all__ = ['calculate_bayes_factors', 'calculate_bayes_factors_for_cells',
           'calculate_bayes_factors_for_one_cell']
