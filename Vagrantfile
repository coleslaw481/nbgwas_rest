# -*- mode: ruby -*-
# vi: set ft=ruby :

# All Vagrant configuration is done below. The "2" in Vagrant.configure
# configures the configuration version (we support older styles for
# backwards compatibility). Please don't change it unless you know what
# you're doing.
Vagrant.configure(2) do |config|
  config.vm.box = "puppetlabs/centos-7.2-64-puppet"
  config.vm.provision :shell, path: "bootstrap.sh"
  config.ssh.forward_x11 = true  
  config.vm.network "forwarded_port", guest: 5000, host: 5000 
  config.vm.network "forwarded_port", guest: 80, host: 8081
  config.vm.network "forwarded_port", guest: 8000, host: 8082
  config.vm.provider "virtualbox" do |vb|
    vb.memory = "6144"
    vb.cpus = "2"
  end
end
