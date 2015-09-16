"""
Class representing a Truncated Normal distribution, with a=0 and b-> inf, 
allowing us to sample from it, and compute the expectation and the variance.

This is the special case that we want to compute the expectation and variance
for multiple independent variables - i.e. mu and tau are vectors.

truncnorm: a, b = (myclip_a - my_mean) / my_std, (myclip_b - my_mean) / my_std
           loc, scale = mu, sigma
           
We get efficient draws using the library rtnorm by C. Lassner, from:
    http://miv.u-strasbg.fr/mazet/rtnorm/
We compute the expectation and variance ourselves - note that we use the
complementary error function for 1-cdf(x) = 0.5*erfc(x/sqrt(2)), as for large
x (>8), cdf(x)=1., so we get 0. instead of something like n*e^-n.

As mu gets lower (negative), and tau higher, we get draws and expectations that
are closer to an exponential distribution with scale parameter mu * tau.

The draws in this case work effectively, but computing the mean and variance
fails due to numerical errors. As a result, the mean and variance go to 0 after
a certain point.
This point is: -38 * std.

This means that we need to use the mean and variance of an exponential when
|mu| gets close to 38*std.
Therefore we use it when |mu| < 30*std.
"""
import math, numpy
import matplotlib.pyplot as plt
from scipy.stats import truncnorm, norm
from scipy.special import erfc
import rtnorm

class TruncatedNormalVector:
    def __init__(self,mu,tau):
        # Mu and tau are now vectors
        self.mu = numpy.array(mu,dtype=numpy.float64)
        self.tau = numpy.array(tau,dtype=numpy.float64)
        self.sigma = numpy.float64(1.0) / numpy.sqrt(self.tau)
        self.a = - self.mu / self.sigma
        self.b = [numpy.inf for m in self.mu]
        
    # Draw a value for x ~ TruncatedNormal(mu,tau). If we get inf we set it to 0.
    def draw(self):
        draws = []
        for (mu,sigma,tau) in zip(self.mu,self.sigma,self.tau):
            if tau == 0.:
                draws.append(0)
            else:
                d = rtnorm.rtnorm(a=0., b=numpy.inf, mu=mu, sigma=sigma)[0]
                d = d if (d >= 0. and d != numpy.inf and d != -numpy.inf and not numpy.isnan(d)) else 0.
                draws.append(d)
        return draws        
        
    # Return expectation. x = - self.mu / self.sigma; lambdax = norm.pdf(x)/(1-norm.cdf(x)); return self.mu + self.sigma * lambdax
    def expectation(self):
        # TN expectation
        x = - self.mu / self.sigma
        lambdax = norm.pdf(x)/(0.5*erfc(x/math.sqrt(2)))
        exp = self.mu + self.sigma * lambdax
        
        # Exp expectation - overwrite value if mu < -30*sigma
        exp = [1./(numpy.abs(mu)*tau) if mu < -30 * sigma else v for v,mu,tau,sigma in zip(exp,self.mu,self.tau,self.sigma)]
        
        return [v if (v >= 0.0 and v != numpy.inf and v != -numpy.inf and not numpy.isnan(v)) else 0. for v in exp]
    
    # Return variance. The library gives NaN for this due to b->inf, so we compute it ourselves
    def variance(self):
        # TN variance
        x = - self.mu / self.sigma
        lambdax = norm.pdf(x)/(0.5*erfc(x/math.sqrt(2)))
        deltax = lambdax*(lambdax-x)
        var = self.sigma**2 * ( 1 - deltax )
        
        # Exp variance - overwrite value if mu < -30*sigma
        var = [(1./(numpy.abs(mu)*tau))**2 if mu < -30 * sigma else v for v,mu,tau,sigma in zip(var,self.mu,self.tau,self.sigma)]
        
        return [v if (v >= 0.0 and v != numpy.inf and v != -numpy.inf and not numpy.isnan(v)) else 0. for v in var]
    